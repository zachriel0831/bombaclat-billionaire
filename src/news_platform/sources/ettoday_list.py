"""ETtoday 分類列表 HTML 解析器。

ETtoday 的分類 RSS 並非每個分類都有穩定 endpoint；政治分類改抓官方
``news-list-YYYY-MM-DD-1.htm`` 頁面，解析列表中的日期、分類標籤與標題連結。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin

from news_platform.author_metadata import (
    AUTHOR_METHOD_NONE,
    AUTHOR_STATUS_PARSER_NOT_SUPPORTED,
)
from news_platform.http_client import http_get_bytes
from news_platform.models import NewsArticle
from news_platform.sources.base import NewsSource
from news_platform.utils import canonical_url, is_recent, sort_timestamp, stable_id


logger = logging.getLogger(__name__)

_TAIPEI = timezone(timedelta(hours=8))
_ETTODAY_BASE_URL = "https://www.ettoday.net/"


@dataclass
class _ListRow:
    date_parts: list[str] = field(default_factory=list)
    tag_parts: list[str] = field(default_factory=list)
    title_parts: list[str] = field(default_factory=list)
    href: str = ""


class _EttodayListParser(HTMLParser):
    def __init__(self, *, expected_tag: str) -> None:
        super().__init__(convert_charrefs=True)
        self.expected_tag = expected_tag
        self.rows: list[_ListRow] = []
        self._row: _ListRow | None = None
        self._field: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        if tag == "h3":
            self._row = _ListRow()
            self._field = None
            return
        if self._row is None:
            return
        if tag == "span" and "date" in attrs_dict.get("class", "").split():
            self._field = "date"
            return
        if tag == "em":
            self._field = "tag"
            return
        if tag == "a":
            self._row.href = attrs_dict.get("href", "")
            self._field = "title"

    def handle_data(self, data: str) -> None:
        if self._row is None or self._field is None:
            return
        text = data.strip()
        if not text:
            return
        if self._field == "date":
            self._row.date_parts.append(text)
        elif self._field == "tag":
            self._row.tag_parts.append(text)
        elif self._field == "title":
            self._row.title_parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        if self._row is None:
            return
        if tag in {"span", "em", "a"}:
            self._field = None
            return
        if tag == "h3":
            tag_text = _collapse(self._row.tag_parts)
            if tag_text == self.expected_tag:
                self.rows.append(self._row)
            self._row = None
            self._field = None


class EttodayNewsListSource(NewsSource):
    def __init__(
        self,
        *,
        source_id: str,
        country: str,
        category: str,
        url: str,
        expected_tag: str = "政治",
        timeout_seconds: int = 15,
        max_age_days: int = 3,
    ) -> None:
        self.source_id = source_id
        self.country = country
        self.category = category
        self.url = url
        self.expected_tag = expected_tag
        self.timeout_seconds = timeout_seconds
        self.max_age_days = max_age_days
        self.name = f"{source_id}:{category}"

    def fetch(self, limit: int = 20) -> list[NewsArticle]:
        articles: list[NewsArticle] = []
        for source_url in self._source_urls():
            try:
                # ETtoday's site certificate can fail Python's strict SKI check on
                # some Windows/OpenSSL builds. This is public read-only HTML, so
                # keep the SSL workaround scoped to this source.
                payload = http_get_bytes(
                    source_url,
                    timeout=self.timeout_seconds,
                    verify_ssl=False,
                )
            except Exception as exc:
                logger.warning("ETtoday list fetch failed source=%s url=%s error=%s", self.name, source_url, exc)
                continue
            articles.extend(self.parse(payload, source_url=source_url))
            if len(articles) >= max(int(limit), 1):
                break
        articles = _dedupe_articles(articles)
        if not articles:
            logger.warning("ETtoday list empty source=%s url=%s", self.name, self.url)
        articles.sort(key=lambda a: sort_timestamp(a.published_at), reverse=True)
        return articles[: max(int(limit), 1)]

    def parse(self, payload: bytes | str, *, source_url: str | None = None) -> list[NewsArticle]:
        text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
        parser = _EttodayListParser(expected_tag=self.expected_tag)
        parser.feed(text)
        articles: list[NewsArticle] = []
        for row in parser.rows:
            article = self._row_to_article(row, source_url=source_url or self.url)
            if article is None:
                continue
            if not is_recent(article.published_at, max_age_days=self.max_age_days):
                continue
            articles.append(article)
        return articles

    def _row_to_article(self, row: _ListRow, *, source_url: str) -> NewsArticle | None:
        title = _collapse(row.title_parts)
        href = row.href.strip()
        if not title or not href:
            return None

        published = _parse_ettoday_datetime(_collapse(row.date_parts))
        original_url = urljoin(_ETTODAY_BASE_URL, href)
        canonical = canonical_url(original_url) or original_url
        tag = _collapse(row.tag_parts)

        return NewsArticle(
            article_id=stable_id(self.source_id, self.category, canonical, title),
            source_id=self.source_id,
            country=self.country,
            category=self.category,
            title=title,
            url=canonical,
            published_at=published,
            summary=None,
            author_extraction_status=AUTHOR_STATUS_PARSER_NOT_SUPPORTED,
            author_extraction_method=AUTHOR_METHOD_NONE,
            tags=[tag] if tag else [],
            raw={
                "feed": source_url,
                "original_url": original_url,
                "kind": "ettoday_list",
                "category_tag": tag,
            },
        )

    def _source_urls(self) -> list[str]:
        if "{date}" not in self.url:
            return [self.url]
        today = datetime.now(_TAIPEI).date()
        day_count = max(1, min(int(self.max_age_days) + 1, 7))
        return [
            self.url.format(date=(today - timedelta(days=offset)).isoformat())
            for offset in range(day_count)
        ]


def _collapse(parts: list[str]) -> str:
    return unescape(" ".join(" ".join(parts).split())).strip()


def _parse_ettoday_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y/%m/%d %H:%M").replace(tzinfo=_TAIPEI)
    except ValueError:
        return None


def _dedupe_articles(articles: list[NewsArticle]) -> list[NewsArticle]:
    seen: set[str] = set()
    output: list[NewsArticle] = []
    for article in articles:
        key = article.article_id or article.url
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(article)
    return output
