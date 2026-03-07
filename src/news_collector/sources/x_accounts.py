from __future__ import annotations

import logging
import re
import time
from urllib.parse import urlparse

from news_collector.http_client import http_get_json_with_headers
from news_collector.models import NewsItem
from news_collector.sources.base import NewsSource
from news_collector.utils import parse_datetime, sort_timestamp


logger = logging.getLogger(__name__)

_X_MIN_REQUEST_INTERVAL_SECONDS = 1.2
_LAST_X_REQUEST_TS = 0.0
_X_STOPPED_BY_429 = False
_X_USER_ID_CACHE: dict[str, str] = {}
_X_SINCE_ID_CACHE: dict[str, str] = {}


def _throttle_x_requests() -> None:
    global _LAST_X_REQUEST_TS
    now = time.monotonic()
    wait_seconds = _X_MIN_REQUEST_INTERVAL_SECONDS - (now - _LAST_X_REQUEST_TS)
    if wait_seconds > 0:
        time.sleep(wait_seconds)
    _LAST_X_REQUEST_TS = time.monotonic()


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


class XAccountSource(NewsSource):
    name = "x_accounts"
    users_lookup_endpoint = "https://api.x.com/2/users/by"
    user_tweets_endpoint = "https://api.x.com/2/users/{user_id}/tweets"

    def __init__(
        self,
        bearer_token: str,
        accounts: list[str],
        timeout_seconds: int = 15,
        max_results_per_account: int = 5,
        stop_on_429: bool = True,
        include_replies: bool = False,
        include_retweets: bool = False,
    ) -> None:
        self._bearer_token = bearer_token.strip()
        self._accounts = accounts
        self._timeout_seconds = timeout_seconds
        self._max_results_per_account = max(1, min(100, int(max_results_per_account)))
        self._stop_on_429 = bool(stop_on_429)
        self._include_replies = bool(include_replies)
        self._include_retweets = bool(include_retweets)

    def fetch(self, limit: int = 20) -> list[NewsItem]:
        global _X_STOPPED_BY_429

        if self._stop_on_429 and _X_STOPPED_BY_429:
            logger.warning("X source stopped by X_STOP_ON_429 after previous 429; skip this cycle")
            return []

        accounts = [name for name in (_normalize_account(x) for x in self._accounts) if name]
        if not accounts:
            logger.warning("X source has no valid accounts configured")
            return []

        user_id_map = self._resolve_user_ids(accounts)
        if not user_id_map:
            return []

        all_items: list[NewsItem] = []
        raw_tweet_count = 0
        for username, user_id in user_id_map.items():
            if self._stop_on_429 and _X_STOPPED_BY_429:
                break

            endpoint = self.user_tweets_endpoint.format(user_id=user_id)
            params: dict[str, str | int] = {
                "max_results": min(self._max_results_per_account, max(limit, 1), 100),
                "tweet.fields": "created_at,lang,public_metrics,conversation_id,referenced_tweets",
            }
            exclude_parts: list[str] = []
            if not self._include_replies:
                exclude_parts.append("replies")
            if not self._include_retweets:
                exclude_parts.append("retweets")
            if exclude_parts:
                params["exclude"] = ",".join(exclude_parts)

            since_id = _X_SINCE_ID_CACHE.get(user_id)
            if since_id:
                params["since_id"] = since_id

            payload = self._request_json(endpoint, params=params)
            if payload is None:
                continue

            tweets = payload.get("data")
            if not isinstance(tweets, list) or not tweets:
                continue

            raw_tweet_count += len(tweets)
            latest_id = since_id or "0"
            for tweet in sorted(tweets, key=lambda x: int(str(x.get("id") or "0"))):
                tweet_id = str(tweet.get("id") or "").strip()
                text = str(tweet.get("text") or "").strip()
                if not tweet_id or not text:
                    continue

                if int(tweet_id) > int(latest_id):
                    latest_id = tweet_id

                created_at = parse_datetime(str(tweet.get("created_at") or ""))
                tweet_url = f"https://x.com/{username}/status/{tweet_id}"
                title = self._tweet_title(text)
                tags: list[str] = [f"account:{username}"]
                lang = str(tweet.get("lang") or "").strip().lower()
                if lang:
                    tags.append(f"lang:{lang}")

                all_items.append(
                    NewsItem(
                        id=f"x-{tweet_id}",
                        source=f"x:{username}",
                        title=title,
                        url=tweet_url,
                        published_at=created_at,
                        summary=text,
                        tags=sorted(set(tags)),
                        raw={"tweet": tweet, "username": username, "user_id": user_id},
                    )
                )

            if int(latest_id) > int(since_id or "0"):
                _X_SINCE_ID_CACHE[user_id] = latest_id

        all_items.sort(key=lambda x: sort_timestamp(x.published_at), reverse=True)
        # 不在這裡做全域截斷，避免 since_id 前進後把未輸出的貼文永久跳過。
        output = all_items
        logger.info(
            "X poll accounts=%d raw_tweets=%d output=%d",
            len(user_id_map),
            raw_tweet_count,
            len(output),
        )
        return output

    def _resolve_user_ids(self, usernames: list[str]) -> dict[str, str]:
        missing = [name for name in usernames if name not in _X_USER_ID_CACHE]
        if missing:
            payload = self._request_json(
                self.users_lookup_endpoint,
                params={
                    "usernames": ",".join(missing),
                    "user.fields": "id,name,username",
                },
            )
            if payload is not None:
                for obj in payload.get("data", []) if isinstance(payload.get("data"), list) else []:
                    if not isinstance(obj, dict):
                        continue
                    username = str(obj.get("username") or "").strip().lower()
                    user_id = str(obj.get("id") or "").strip()
                    if username and user_id:
                        _X_USER_ID_CACHE[username] = user_id

                for err in payload.get("errors", []) if isinstance(payload.get("errors"), list) else []:
                    detail = str(err.get("detail") or err) if isinstance(err, dict) else str(err)
                    logger.warning("X users lookup warning: %s", detail)

        return {username: _X_USER_ID_CACHE[username] for username in usernames if username in _X_USER_ID_CACHE}

    def _request_json(self, url: str, params: dict[str, str | int]) -> dict | None:
        global _X_STOPPED_BY_429
        try:
            _throttle_x_requests()
            return http_get_json_with_headers(
                url,
                params=params,
                timeout=self._timeout_seconds,
                headers={"Authorization": f"Bearer {self._bearer_token}"},
            )
        except Exception as exc:
            text = str(exc)
            is_429 = "429" in text
            if is_429 and self._stop_on_429:
                _X_STOPPED_BY_429 = True
                logger.warning("X source got 429 and X_STOP_ON_429=true, stop polling until restart")
                return None
            if is_429:
                logger.warning("X source rate-limited (429), skip current request")
                return None

            logger.warning("X request failed url=%s error=%s", url, exc)
            return None

    @staticmethod
    def _tweet_title(text: str) -> str:
        compact = " ".join(text.split()).strip()
        if len(compact) <= 140:
            return compact
        return compact[:137] + "..."
