"""Truth Social account timeline source.

Polls configured public Truth Social accounts through the Mastodon-compatible
public endpoints and normalizes statuses into ``NewsItem`` rows.
"""

from __future__ import annotations

import html
import logging
import re
from urllib.parse import urlparse

from news_collector.http_client import http_get_json_with_headers
from news_collector.models import NewsItem
from news_collector.sources.base import NewsSource
from news_collector.utils import parse_datetime, sort_timestamp


logger = logging.getLogger(__name__)

TRUTH_SOCIAL_BASE_URL = "https://truthsocial.com"
_TRUTH_ACCOUNT_ID_CACHE: dict[str, str] = {}
_TRUTH_SINCE_ID_CACHE: dict[str, str] = {}


def _normalize_account(raw: str) -> str | None:
    """Normalize a Truth Social handle or profile URL to lowercase username."""
    text = (raw or "").strip()
    if not text:
        return None

    lowered = text.lower()
    if lowered.startswith("truthsocial:"):
        text = text.split(":", 1)[1]
    elif lowered.startswith("truth:"):
        text = text.split(":", 1)[1]

    if text.startswith(("http://", "https://")):
        parsed = urlparse(text)
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        if host != "truthsocial.com":
            return None
        segments = [seg.strip() for seg in parsed.path.split("/") if seg.strip()]
        if not segments:
            return None
        if segments[0].startswith("@"):
            text = segments[0][1:]
        elif len(segments) >= 2 and segments[0].lower() == "users":
            text = segments[1]
        else:
            text = segments[0]

    if text.startswith("@"):
        text = text[1:]
    text = text.strip()
    if not re.fullmatch(r"[A-Za-z0-9_]{1,64}", text):
        return None
    return text.lower()


def _plain_text_from_html(value: str | None) -> str:
    """Convert Truth Social status HTML into compact display text."""
    text = str(value or "")
    if not text:
        return ""
    text = re.sub(r"</(?:p|div|li|h[1-6])>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(html.unescape(text).split()).strip()


def _display_account(username: str) -> str:
    known = {"realdonaldtrump": "Donald Trump"}
    return known.get(username.lower(), f"@{username}")


def _media_text(value: object, *, username: str) -> str:
    if not isinstance(value, list) or not value:
        return ""

    kinds: list[str] = []
    for media in value:
        if not isinstance(media, dict):
            continue
        description = _plain_text_from_html(str(media.get("description") or ""))
        if description:
            return description
        kind = str(media.get("type") or "").strip().lower()
        if kind:
            kinds.append(kind)

    if "video" in kinds:
        label = "a video"
    elif "image" in kinds:
        label = "an image"
    elif "gifv" in kinds:
        label = "a GIF"
    else:
        label = "media"
    return f"{_display_account(username)} shared {label} on Truth Social"


class TruthSocialAccountSource(NewsSource):
    """Truth Social account timeline source."""

    name = "truth_social_accounts"
    account_lookup_endpoint = f"{TRUTH_SOCIAL_BASE_URL}/api/v1/accounts/lookup"
    account_statuses_endpoint = f"{TRUTH_SOCIAL_BASE_URL}/api/v1/accounts/{{account_id}}/statuses"

    def __init__(
        self,
        accounts: list[str],
        timeout_seconds: int = 15,
        max_results_per_account: int = 10,
        user_agent: str | None = None,
    ) -> None:
        self._accounts = accounts
        self._timeout_seconds = timeout_seconds
        self._max_results_per_account = max(1, min(40, int(max_results_per_account)))
        self._user_agent = (user_agent or "").strip()

    def fetch(self, limit: int = 20) -> list[NewsItem]:
        accounts = [name for name in (_normalize_account(x) for x in self._accounts) if name]
        if not accounts:
            logger.warning("Truth Social source has no valid accounts configured")
            return []

        account_id_map = self._resolve_account_ids(accounts)
        if not account_id_map:
            return []

        all_items: list[NewsItem] = []
        raw_status_count = 0
        for username, account_id in account_id_map.items():
            endpoint = self.account_statuses_endpoint.format(account_id=account_id)
            request_limit = min(self._max_results_per_account, max(limit, 1), 40)
            params: dict[str, str | int] = {
                "limit": request_limit,
                "exclude_replies": "true",
                "exclude_reblogs": "true",
                "with_muted": "true",
            }
            since_id = _TRUTH_SINCE_ID_CACHE.get(account_id)
            if since_id:
                params["since_id"] = since_id

            payload = self._request_json(endpoint, params=params)
            statuses = payload.get("data")
            if not isinstance(statuses, list) or not statuses:
                continue

            statuses = statuses[:request_limit]
            raw_status_count += len(statuses)
            latest_id = int(since_id or "0")
            for status in sorted(statuses, key=lambda item: int(str(item.get("id") or "0"))):
                item = self._to_news_item(status, username=username, account_id=account_id)
                if item is None:
                    continue
                try:
                    latest_id = max(latest_id, int(item.id.split("-", 1)[1]))
                except (IndexError, ValueError):
                    pass
                all_items.append(item)

            if latest_id > int(since_id or "0"):
                _TRUTH_SINCE_ID_CACHE[account_id] = str(latest_id)

        all_items.sort(key=lambda x: sort_timestamp(x.published_at), reverse=True)
        logger.info(
            "Truth Social poll accounts=%d raw_statuses=%d output=%d",
            len(account_id_map),
            raw_status_count,
            len(all_items),
        )
        return all_items

    def _resolve_account_ids(self, usernames: list[str]) -> dict[str, str]:
        missing = [name for name in usernames if name not in _TRUTH_ACCOUNT_ID_CACHE]
        for username in missing:
            payload = self._request_json(self.account_lookup_endpoint, params={"acct": username})
            account_id = str(payload.get("id") or "").strip()
            resolved_username = str(payload.get("username") or username).strip().lower()
            if account_id:
                _TRUTH_ACCOUNT_ID_CACHE[resolved_username] = account_id
                _TRUTH_ACCOUNT_ID_CACHE[username] = account_id

        return {username: _TRUTH_ACCOUNT_ID_CACHE[username] for username in usernames if username in _TRUTH_ACCOUNT_ID_CACHE}

    def _to_news_item(self, status: dict, *, username: str, account_id: str) -> NewsItem | None:
        status_id = str(status.get("id") or "").strip()
        if not status_id:
            return None

        text = _plain_text_from_html(str(status.get("content") or ""))
        if not text:
            card = status.get("card")
            if isinstance(card, dict):
                text = " ".join(
                    part
                    for part in [
                        str(card.get("title") or "").strip(),
                        str(card.get("description") or "").strip(),
                    ]
                    if part
                ).strip()
        if not text:
            text = _media_text(status.get("media_attachments"), username=username)
        if not text:
            text = f"{_display_account(username)} published a Truth Social post without text"

        published_at = parse_datetime(str(status.get("created_at") or ""))
        post_url = str(status.get("url") or status.get("uri") or "").strip()
        if not post_url:
            post_url = f"{TRUTH_SOCIAL_BASE_URL}/@{username}/{status_id}"

        lang = str(status.get("language") or "").strip().lower()
        tags = [f"account:{username}", "platform:truthsocial"]
        if lang:
            tags.append(f"lang:{lang}")

        metrics = {
            key: status.get(key)
            for key in (
                "replies_count",
                "reblogs_count",
                "favourites_count",
                "upvotes_count",
                "downvotes_count",
            )
            if status.get(key) is not None
        }

        return NewsItem(
            id=f"truthsocial-{status_id}",
            source=f"truthsocial:{username}",
            title=self._status_title(text),
            url=post_url,
            published_at=published_at,
            summary=text,
            tags=sorted(set(tags)),
            raw={
                "truth": status,
                "username": username,
                "account_id": account_id,
                "platform": "truthsocial",
                "metrics": metrics,
            },
        )

    def _request_json(self, url: str, params: dict[str, str | int]) -> dict:
        headers = {"Accept": "application/json"}
        if self._user_agent:
            headers["User-Agent"] = self._user_agent
        return http_get_json_with_headers(
            url,
            params=params,
            timeout=self._timeout_seconds,
            headers=headers,
        )

    @staticmethod
    def _status_title(text: str) -> str:
        compact = " ".join(text.split()).strip()
        if len(compact) <= 140:
            return compact
        return compact[:137] + "..."
