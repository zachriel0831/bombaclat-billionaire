"""通用 RSS / Atom 解析器 — 一個 source_id + category 對一個 feed URL。

不直接打外網的解析路徑：純 bytes/字串 → NewsArticle，方便單元測試以 fixture 餵入。
"""

from __future__ import annotations

import logging
from xml.etree import ElementTree as ET

from news_platform.http_client import http_get_bytes
from news_platform.models import NewsArticle
from news_platform.sources.base import NewsSource
from news_platform.utils import (
    canonical_url,
    clean_summary,
    is_recent,
    local_name,
    parse_datetime,
    sort_timestamp,
    stable_id,
)


logger = logging.getLogger(__name__)


class RssFeedSource(NewsSource):
    def __init__(
        self,
        *,
        source_id: str,
        country: str,
        category: str,
        url: str,
        timeout_seconds: int = 15,
        max_age_days: int = 3,
    ) -> None:
        self.source_id = source_id
        self.country = country
        self.category = category
        self.url = url
        self.timeout_seconds = timeout_seconds
        self.max_age_days = max_age_days
        self.name = f"{source_id}:{category}"

    def fetch(self, limit: int = 20) -> list[NewsArticle]:
        try:
            payload = http_get_bytes(self.url, timeout=self.timeout_seconds)
        except Exception as exc:
            logger.warning("RSS fetch failed source=%s url=%s error=%s", self.name, self.url, exc)
            return []
        articles = self.parse(payload)
        if not articles:
            logger.warning("RSS empty source=%s url=%s", self.name, self.url)
        articles.sort(key=lambda a: sort_timestamp(a.published_at), reverse=True)
        return articles[: max(int(limit), 1)]

    def parse(self, payload: bytes | str) -> list[NewsArticle]:
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as exc:
            logger.warning("RSS parse failed source=%s error=%s", self.name, exc)
            return []

        nodes = root.findall(".//item") + root.findall(".//{*}entry")
        articles: list[NewsArticle] = []
        for node in nodes:
            article = self._node_to_article(node)
            if article is None:
                continue
            if not is_recent(article.published_at, max_age_days=self.max_age_days):
                continue
            articles.append(article)
        return articles

    def _node_to_article(self, node: ET.Element) -> NewsArticle | None:
        title = self._text(node, "title")
        if not title:
            return None
        link = self._link(node)
        if not link:
            return None

        canonical = canonical_url(link) or link
        published = parse_datetime(self._text(node, "pubDate", "published", "updated"))
        summary = clean_summary(self._text(node, "description", "summary", "content"))

        tags: list[str] = []
        for child in list(node):
            if local_name(child.tag).lower() == "category":
                term = (child.attrib.get("term") or child.text or "").strip()
                if term:
                    tags.append(term)

        return NewsArticle(
            article_id=stable_id(self.source_id, self.category, canonical, title.strip()),
            source_id=self.source_id,
            country=self.country,
            category=self.category,
            title=title.strip(),
            url=canonical,
            published_at=published,
            summary=summary,
            tags=sorted(set(tags)),
            raw={"feed": self.url, "original_url": link},
        )

    @staticmethod
    def _text(node: ET.Element, *names: str) -> str | None:
        for name in names:
            direct = node.findtext(name)
            if direct and direct.strip():
                return direct
            for child in list(node):
                if local_name(child.tag).lower() == name.lower() and (child.text or "").strip():
                    return child.text
        return None

    @staticmethod
    def _link(node: ET.Element) -> str | None:
        direct = node.findtext("link")
        if direct and direct.strip():
            return direct.strip()
        for child in list(node):
            if local_name(child.tag).lower() == "link":
                href = child.attrib.get("href")
                if href:
                    return href.strip()
                if (child.text or "").strip():
                    return child.text.strip()
        return None
