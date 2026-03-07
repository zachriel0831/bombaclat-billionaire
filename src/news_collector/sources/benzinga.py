from __future__ import annotations

# Benzinga REST 來源抓取與欄位正規化。
from news_collector.http_client import http_get_json
from news_collector.models import NewsItem
from news_collector.sources.base import NewsSource
from news_collector.utils import parse_datetime, stable_id


class BenzingaSource(NewsSource):
    name = "benzinga"
    endpoint = "https://api.benzinga.com/api/v2/news"

    def __init__(self, api_key: str, timeout_seconds: int = 15) -> None:
        if not api_key:
            raise ValueError("BENZINGA_API_KEY is required for Benzinga source.")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def fetch(self, limit: int = 20) -> list[NewsItem]:
        params = {
            "token": self.api_key,
            "pageSize": max(limit, 1),
            "displayOutput": "headline",
        }
        payload = http_get_json(self.endpoint, params=params, timeout=self.timeout_seconds)

        records = payload.get("data", payload)
        if isinstance(records, dict):
            records = records.get("data", [])
        if not isinstance(records, list):
            records = []

        items: list[NewsItem] = []
        for rec in records:
            title = rec.get("title") or rec.get("headline") or "(untitled)"
            url = rec.get("url") or rec.get("link") or ""
            published = parse_datetime(
                rec.get("created")
                or rec.get("updated")
                or rec.get("published")
                or rec.get("date")
            )

            tags: list[str] = []
            for symbol in rec.get("stocks", []) or rec.get("symbols", []):
                if isinstance(symbol, str):
                    tags.append(symbol)
                elif isinstance(symbol, dict) and symbol.get("name"):
                    tags.append(symbol["name"])

            for channel in rec.get("channels", []):
                if isinstance(channel, str):
                    tags.append(channel)
                elif isinstance(channel, dict):
                    name = channel.get("name") or channel.get("slug")
                    if name:
                        tags.append(str(name))

            items.append(
                NewsItem(
                    id=str(rec.get("id") or stable_id("benzinga", title, url)),
                    source="benzinga",
                    title=title,
                    url=url,
                    published_at=published,
                    summary=rec.get("teaser") or rec.get("body") or None,
                    tags=sorted(set(tags)),
                    raw=rec,
                )
            )

        return items[:limit]
