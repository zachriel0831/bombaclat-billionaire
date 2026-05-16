"""Google News sitemap 解析器。

針對 ``<urlset>`` + ``<news:news>`` namespace 的 sitemap（Google News
sitemap protocol）。每筆 ``<url>`` 拿 ``<loc>``、``<news:title>``、
``<news:publication_date>`` 組成 NewsArticle。可用 ``path_filter`` 過濾
分類路徑（例：TVBS 的 ``/local/`` 對應社會分版）。
"""

from __future__ import annotations

import logging
from xml.etree import ElementTree as ET

from news_platform.author_metadata import (
    AUTHOR_METHOD_NONE,
    AUTHOR_METHOD_SITEMAP_METADATA,
    AUTHOR_STATUS_LOW_CONFIDENCE,
    AUTHOR_STATUS_NO_DETAIL_FETCHED,
    AUTHOR_STATUS_PRESENT,
)
from news_platform.author_extractor import normalize_authors
from news_platform.http_client import http_get_bytes
from news_platform.models import NewsArticle
from news_platform.sources.base import NewsSource
from news_platform.utils import (
    canonical_url,
    is_recent,
    local_name,
    parse_datetime,
    sort_timestamp,
    stable_id,
)


logger = logging.getLogger(__name__)


class GoogleNewsSitemapSource(NewsSource):
    def __init__(
        self,
        *,
        source_id: str,
        country: str,
        category: str,
        url: str,
        path_filter: str | None = None,
        timeout_seconds: int = 15,
        max_age_days: int = 3,
    ) -> None:
        self.source_id = source_id
        self.country = country
        self.category = category
        self.url = url
        self.path_filter = path_filter
        self.timeout_seconds = timeout_seconds
        self.max_age_days = max_age_days
        self.name = f"{source_id}:{category}"

    def fetch(self, limit: int = 20) -> list[NewsArticle]:
        try:
            payload = http_get_bytes(self.url, timeout=self.timeout_seconds)
        except Exception as exc:
            logger.warning("Sitemap fetch failed source=%s url=%s error=%s", self.name, self.url, exc)
            return []
        articles = self.parse(payload)
        if not articles:
            logger.warning("Sitemap empty source=%s url=%s", self.name, self.url)
        articles.sort(key=lambda a: sort_timestamp(a.published_at), reverse=True)
        return articles[: max(int(limit), 1)]

    def parse(self, payload: bytes | str) -> list[NewsArticle]:
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as exc:
            logger.warning("Sitemap parse failed source=%s error=%s", self.name, exc)
            return []

        # 用 ``{*}`` 通配 namespace，sitemap 與 news 兩組都 cover 到。
        url_nodes = root.findall(".//{*}url")
        articles: list[NewsArticle] = []
        for node in url_nodes:
            article = self._node_to_article(node)
            if article is None:
                continue
            if not is_recent(article.published_at, max_age_days=self.max_age_days):
                continue
            articles.append(article)
        return articles

    def _node_to_article(self, node: ET.Element) -> NewsArticle | None:
        loc = self._find_text(node, "loc")
        if not loc:
            return None
        if self.path_filter and self.path_filter not in loc:
            return None

        news_node = self._find_child(node, "news")
        if news_node is None:
            return None

        title = self._find_text(news_node, "title")
        if not title:
            return None

        published = parse_datetime(self._find_text(news_node, "publication_date"))
        canonical = canonical_url(loc) or loc
        author_values = self._find_texts(news_node, "author", "creator")
        authors = normalize_authors(author_values)
        author_status = AUTHOR_STATUS_NO_DETAIL_FETCHED
        author_method = AUTHOR_METHOD_NONE
        author_confidence: float | None = None
        author_raw_text: str | None = None
        if author_values:
            author_raw_text = " | ".join(author_values)
            author_method = AUTHOR_METHOD_SITEMAP_METADATA
            if authors:
                author_status = AUTHOR_STATUS_PRESENT
                author_confidence = 1.0
            else:
                author_status = AUTHOR_STATUS_LOW_CONFIDENCE
                author_confidence = 0.0
        publication_name = self._publication_name(news_node)

        return NewsArticle(
            article_id=stable_id(self.source_id, self.category, canonical, title.strip()),
            source_id=self.source_id,
            country=self.country,
            category=self.category,
            title=title.strip(),
            url=canonical,
            published_at=published,
            summary=None,
            authors=authors,
            author_extraction_status=author_status,
            author_extraction_method=author_method,
            author_extraction_confidence=author_confidence,
            author_raw_text=author_raw_text,
            tags=[],
            raw=self._raw_payload(loc, author_values, publication_name),
        )

    @staticmethod
    def _find_text(parent: ET.Element, name: str) -> str | None:
        for child in parent.iter():
            if local_name(child.tag).lower() == name.lower():
                value = (child.text or "").strip()
                if value:
                    return value
        return None

    @staticmethod
    def _find_child(parent: ET.Element, name: str) -> ET.Element | None:
        for child in parent.iter():
            if local_name(child.tag).lower() == name.lower():
                return child
        return None

    @staticmethod
    def _find_texts(parent: ET.Element, *names: str) -> list[str]:
        wanted = {name.lower() for name in names}
        values: list[str] = []
        for child in parent.iter():
            if local_name(child.tag).lower() in wanted:
                value = (child.text or "").strip()
                if value:
                    values.append(value)
        return values

    @staticmethod
    def _publication_name(news_node: ET.Element) -> str | None:
        publication = GoogleNewsSitemapSource._find_child(news_node, "publication")
        if publication is None:
            return None
        return GoogleNewsSitemapSource._find_text(publication, "name")

    def _raw_payload(
        self,
        original_url: str,
        author_values: list[str],
        publication_name: str | None,
    ) -> dict[str, object]:
        raw: dict[str, object] = {
            "feed": self.url,
            "original_url": original_url,
            "kind": "sitemap",
        }
        if author_values:
            raw["author_values"] = author_values
        if publication_name:
            raw["publication_name"] = publication_name
        return raw
