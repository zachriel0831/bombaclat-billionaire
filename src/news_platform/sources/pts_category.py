"""PTS category-page parser for society/politics news."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin

from news_platform.http_client import http_get_bytes
from news_platform.models import NewsArticle
from news_platform.sources.base import NewsSource
from news_platform.utils import canonical_url, is_recent, sort_timestamp, stable_id


logger = logging.getLogger(__name__)

_TAIPEI = timezone(timedelta(hours=8))
_PTS_BASE_URL = "https://news.pts.org.tw/"
_ARTICLE_RE = re.compile(r"^https://news\.pts\.org\.tw/article/\d+$")


@dataclass
class _PtsRow:
    href: str
    title_parts: list[str] = field(default_factory=list)
    time_parts: list[str] = field(default_factory=list)
    datetime_text: str = ""


class _PtsCategoryParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[_PtsRow] = []
        self._row: _PtsRow | None = None
        self._field: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        if tag == "a":
            href = _article_url(attrs_dict.get("href", ""))
            if not href:
                return
            if self._row is None or self._row.href != href:
                self._finish_row()
                self._row = _PtsRow(href=href)
            self._field = "title"
            return
        if tag == "time" and self._row is not None:
            self._row.datetime_text = attrs_dict.get("datetime", "").strip()
            self._field = "time"

    def handle_data(self, data: str) -> None:
        if self._row is None or self._field is None:
            return
        text = data.strip()
        if not text:
            return
        if self._field == "title":
            self._row.title_parts.append(text)
        elif self._field == "time":
            self._row.time_parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._field == "title":
            self._field = None
        elif tag == "time" and self._field == "time":
            self._field = None

    def finish(self) -> None:
        self._finish_row()

    def _finish_row(self) -> None:
        if self._row is not None and _collapse(self._row.title_parts):
            self.rows.append(self._row)
        self._row = None
        self._field = None


class PtsCategorySource(NewsSource):
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
            # PTS pages are public read-only HTML. Some local Windows/OpenSSL
            # builds reject their certificate because the SKI extension is absent.
            payload = http_get_bytes(
                self.url,
                timeout=self.timeout_seconds,
                verify_ssl=False,
            )
        except Exception as exc:
            logger.warning("PTS category fetch failed source=%s url=%s error=%s", self.name, self.url, exc)
            return []
        articles = self.parse(payload, source_url=self.url)
        if not articles:
            logger.warning("PTS category empty source=%s url=%s", self.name, self.url)
        articles.sort(key=lambda a: sort_timestamp(a.published_at), reverse=True)
        return articles[: max(int(limit), 1)]

    def parse(self, payload: bytes | str, *, source_url: str | None = None) -> list[NewsArticle]:
        text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
        parser = _PtsCategoryParser()
        parser.feed(text)
        parser.finish()

        articles: list[NewsArticle] = []
        for row in parser.rows:
            article = self._row_to_article(row, source_url=source_url or self.url)
            if article is None:
                continue
            if not is_recent(article.published_at, max_age_days=self.max_age_days):
                continue
            articles.append(article)
        return _dedupe_articles(articles)

    def _row_to_article(self, row: _PtsRow, *, source_url: str) -> NewsArticle | None:
        title = _collapse(row.title_parts)
        if not title:
            return None

        canonical = canonical_url(row.href) or row.href
        published = _parse_pts_datetime(row.datetime_text or _collapse(row.time_parts))

        return NewsArticle(
            article_id=stable_id(self.source_id, self.category, canonical, title),
            source_id=self.source_id,
            country=self.country,
            category=self.category,
            title=title,
            url=canonical,
            published_at=published,
            summary=None,
            tags=[],
            raw={
                "feed": source_url,
                "original_url": row.href,
                "kind": "pts_category",
            },
        )


def _article_url(value: str) -> str:
    if not value:
        return ""
    url = urljoin(_PTS_BASE_URL, value.strip())
    canonical = canonical_url(url) or url
    return canonical if _ARTICLE_RE.match(canonical) else ""


def _collapse(parts: list[str]) -> str:
    return unescape(" ".join(" ".join(parts).split())).strip()


def _parse_pts_datetime(value: str) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=_TAIPEI)
        except ValueError:
            pass
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
