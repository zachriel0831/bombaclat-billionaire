from __future__ import annotations

# X Filtered Stream 封裝：追蹤指定帳號推文，提供近即時事件。
from collections import deque
from dataclasses import dataclass
import json
import logging
import random
import re
import threading
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from news_collector.models import NewsItem
from news_collector.utils import parse_datetime


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class XStreamConfig:
    bearer_token: str
    accounts: list[str]
    include_replies: bool = False
    include_retweets: bool = False
    timeout_seconds: int = 90
    reconnect_max_seconds: int = 120
    stop_on_429: bool = True
    auto_heal_too_many_connections: bool = True
    heal_cooldown_seconds: int = 45


class _StopStream(RuntimeError):
    pass


class XFilteredStreamer:
    rules_endpoint = "https://api.x.com/2/tweets/search/stream/rules"
    stream_endpoint = "https://api.x.com/2/tweets/search/stream"
    connections_endpoint = "https://api.x.com/2/connections"
    terminate_all_connections_endpoint = "https://api.x.com/2/connections/all"
    rule_tag_prefix = "news_collector_x_stream"

    def __init__(self, config: XStreamConfig) -> None:
        self.config = config
        self._seen_limit = 5000
        self._seen_ids: deque[str] = deque()
        self._seen_set: set[str] = set()
        self._last_connection_heal_at = 0.0

    def run(self, on_item: Callable[[NewsItem], None], stop_event: threading.Event) -> None:
        accounts = [name for name in (_normalize_account(x) for x in self.config.accounts) if name]
        if not accounts:
            logger.warning("X stream skipped: no valid accounts configured")
            return

        query = self._build_query(accounts)
        logger.info("X stream tracking query=%s", query)

        try:
            self._sync_rules(query)

            backoff_seconds = 1.0
            # stream 長連線一定會遇到網路斷線 / timeout / 429；
            # 這裡用指數退避重連，並在 finally 清掉自己建立的規則。
            while not stop_event.is_set():
                try:
                    self._consume_stream(on_item=on_item, stop_event=stop_event)
                    backoff_seconds = 1.0
                except _StopStream:
                    return
                except Exception as exc:
                    wait_seconds = min(backoff_seconds, float(self.config.reconnect_max_seconds))
                    jitter = random.uniform(0.0, 0.5)
                    logger.warning("X stream error: %s; reconnect in %.1fs", exc, wait_seconds + jitter)
                    stop_event.wait(wait_seconds + jitter)
                    backoff_seconds = min(backoff_seconds * 2.0, float(self.config.reconnect_max_seconds))
        finally:
            # 只清理本服務建立的規則，避免干擾其他工具。
            self._clear_owned_rules()

    def _consume_stream(self, on_item: Callable[[NewsItem], None], stop_event: threading.Event) -> None:
        params = {
            "tweet.fields": "created_at,lang,public_metrics,referenced_tweets,author_id",
            "expansions": "author_id",
            "user.fields": "username",
        }
        stream_url = f"{self.stream_endpoint}?{urlencode(params)}"

        req = Request(stream_url, method="GET")
        req.add_header("Authorization", f"Bearer {self.config.bearer_token}")

        try:
            with urlopen(req, timeout=self.config.timeout_seconds) as resp:
                code = int(getattr(resp, "status", 0))
                if code != 200:
                    raise RuntimeError(f"X stream connect failed status={code}")

                logger.info("X filtered stream connected")
                for raw_line in resp:
                    if stop_event.is_set():
                        return

                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        # keep-alive line
                        continue

                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        logger.debug("X stream non-json line=%s", line[:200])
                        continue

                    item = self._to_news_item(payload)
                    if item is None:
                        continue

                    if not self._remember_tweet(item.id):
                        continue

                    on_item(item)
        except HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
            if int(exc.code) == 429:
                # X 最麻煩的是 TooManyConnections；若可自癒就先清掉舊連線再重試，
                # 不行才依設定停流或交給外層 backoff。
                healed = self._auto_heal_too_many_connections(body_text)
                if healed:
                    raise RuntimeError("X stream auto-healed TooManyConnections, retrying") from exc
                if self.config.stop_on_429:
                    logger.warning("X stream got 429 and X_STOP_ON_429=true, stop stream until restart body=%s", body_text[:280])
                    raise _StopStream("x stream stopped on 429") from exc
                raise RuntimeError(f"X stream rate-limited (429) body={body_text}") from exc
            raise RuntimeError(f"X stream HTTPError status={exc.code} body={body_text}") from exc
        except URLError as exc:
            raise RuntimeError(f"X stream URLError: {exc}") from exc

    def _auto_heal_too_many_connections(self, body_text: str) -> bool:
        if not self.config.auto_heal_too_many_connections:
            return False
        if not self._is_too_many_connections_429(body_text):
            return False

        now = time.time()
        if now - self._last_connection_heal_at < max(self.config.heal_cooldown_seconds, 5):
            logger.warning("X stream auto-heal skipped by cooldown (%.1fs)", now - self._last_connection_heal_at)
            return False

        try:
            logger.warning("X stream auto-heal triggered: terminate stale stream connections")
            result = self._request_json(self.terminate_all_connections_endpoint, method="DELETE")
            success, failed = self._parse_connection_kill_stats(result)
            self._last_connection_heal_at = now
            logger.info("X stream auto-heal completed: successful_kills=%d failed_kills=%d", success, failed)
            return success > 0 and failed == 0
        except Exception as exc:
            logger.warning("X stream auto-heal failed: %s", exc)
            return False

    @staticmethod
    def _is_too_many_connections_429(body_text: str) -> bool:
        text = (body_text or "").lower()
        return "toomanyconnections" in text or "maximum allowed connection limit" in text

    @staticmethod
    def _parse_connection_kill_stats(result: dict[str, Any]) -> tuple[int, int]:
        data = result.get("data") if isinstance(result, dict) else None
        if not isinstance(data, dict):
            return 0, 0
        return int(data.get("successful_kills") or 0), int(data.get("failed_kills") or 0)

    def _sync_rules(self, query: str) -> None:
        self._clear_owned_rules()
        payload = {
            "add": [
                {
                    "value": query,
                    "tag": f"{self.rule_tag_prefix}_{int(time.time())}",
                }
            ]
        }
        result = self._request_json(self.rules_endpoint, method="POST", payload=payload)
        if not isinstance(result, dict):
            raise RuntimeError("X rules add returned invalid response")

        errors = result.get("errors")
        data = result.get("data")
        if errors and not data:
            raise RuntimeError(f"X rules add failed: {errors}")

        logger.info("X stream rule synced")

    def _clear_owned_rules(self) -> None:
        try:
            result = self._request_json(self.rules_endpoint, method="GET")
        except Exception as exc:
            logger.warning("X rules fetch failed when clearing owned rules: %s", exc)
            return

        data = result.get("data") if isinstance(result, dict) else None
        if not isinstance(data, list):
            return

        owned_ids: list[str] = []
        for rule in data:
            if not isinstance(rule, dict):
                continue
            tag = str(rule.get("tag") or "")
            rule_id = str(rule.get("id") or "").strip()
            if rule_id and tag.startswith(self.rule_tag_prefix):
                owned_ids.append(rule_id)

        if not owned_ids:
            return

        payload = {"delete": {"ids": owned_ids}}
        try:
            # 只刪本服務 tag 過的規則，避免把同帳號下其他工具的 stream rule 一起清掉。
            self._request_json(self.rules_endpoint, method="POST", payload=payload)
            logger.info("X stream cleaned old rules count=%d", len(owned_ids))
        except Exception as exc:
            logger.warning("X rules delete failed ids=%s error=%s", ",".join(owned_ids), exc)

    def _request_json(self, url: str, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        req = Request(url, data=data, method=method.upper())
        req.add_header("Authorization", f"Bearer {self.config.bearer_token}")
        req.add_header("Content-Type", "application/json")

        with urlopen(req, timeout=max(self.config.timeout_seconds, 15)) as resp:
            text = resp.read().decode("utf-8", errors="replace")

        if not text.strip():
            return {}

        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        return {"data": parsed}

    def _build_query(self, accounts: list[str]) -> str:
        from_terms = [f"from:{name}" for name in accounts]
        query = f"({' OR '.join(from_terms)})"

        if not self.config.include_replies:
            query += " -is:reply"
        if not self.config.include_retweets:
            query += " -is:retweet"
        return query

    def _to_news_item(self, payload: dict[str, Any]) -> NewsItem | None:
        if not isinstance(payload, dict):
            return None

        data = payload.get("data")
        if not isinstance(data, dict):
            return None

        tweet_id = str(data.get("id") or "").strip()
        text = str(data.get("text") or "").strip()
        if not tweet_id or not text:
            return None

        author_id = str(data.get("author_id") or "").strip()
        username = self._resolve_username(payload.get("includes"), author_id) or f"user_{author_id or 'unknown'}"
        username = username.strip().lower()

        created_at = parse_datetime(str(data.get("created_at") or ""))
        lang = str(data.get("lang") or "").strip().lower()
        tags = [f"account:{username}"]
        if lang:
            tags.append(f"lang:{lang}")

        return NewsItem(
            id=f"x-{tweet_id}",
            source=f"x:{username}",
            title=_tweet_title(text),
            url=f"https://x.com/{username}/status/{tweet_id}",
            published_at=created_at,
            summary=text,
            tags=sorted(set(tags)),
            raw={"stream_payload": payload, "tweet": data, "username": username, "user_id": author_id},
        )

    @staticmethod
    def _resolve_username(includes: Any, author_id: str) -> str | None:
        if not isinstance(includes, dict):
            return None
        users = includes.get("users")
        if not isinstance(users, list):
            return None

        for user in users:
            if not isinstance(user, dict):
                continue
            if str(user.get("id") or "").strip() != author_id:
                continue
            username = str(user.get("username") or "").strip()
            if username:
                return username
        return None

    def _remember_tweet(self, item_id: str) -> bool:
        if item_id in self._seen_set:
            return False

        # stream reconnect 時常會再收到剛才那幾筆，這裡用小型 in-memory LRU 先擋一次，
        # 減少 bridge 在短時間內重複送同 tweet。
        self._seen_ids.append(item_id)
        self._seen_set.add(item_id)
        while len(self._seen_ids) > self._seen_limit:
            old = self._seen_ids.popleft()
            self._seen_set.discard(old)
        return True


def _normalize_account(raw: str) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None

    if text.startswith(("http://", "https://")):
        parsed = urlparse(text)
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        if host not in {"x.com", "twitter.com", "mobile.twitter.com"}:
            return None
        segments = [seg.strip() for seg in parsed.path.split("/") if seg.strip()]
        if not segments:
            return None
        text = segments[0]

    if text.startswith("@"):
        text = text[1:]
    text = text.strip()
    if not text:
        return None
    if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", text):
        return None
    return text.lower()


def _tweet_title(text: str) -> str:
    compact = " ".join(text.split()).strip()
    if len(compact) <= 140:
        return compact
    return compact[:137] + "..."
