"""Low-frequency public HTML list sources for Taiwan news pages."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

from news_platform.author_metadata import (
    AUTHOR_METHOD_NONE,
    AUTHOR_STATUS_NO_DETAIL_FETCHED,
)
from news_platform.http_client import http_get_bytes
from news_platform.models import NewsArticle
from news_platform.sources.base import NewsSource
from news_platform.utils import canonical_url, is_recent, parse_datetime, sort_timestamp, stable_id


logger = logging.getLogger(__name__)

_TAIPEI = timezone(timedelta(hours=8))
_TVBS_RE = re.compile(r"^https://news\.tvbs\.com\.tw/(?:local|politics)/\d+/?$")
_UDN_RE = re.compile(r"^https://udn\.com/news/story/\d+/\d+")
_SETN_RE = re.compile(r"^https://www\.setn\.com/news/\d+/?$")
_STORM_RE = re.compile(r"^https://www\.storm\.mg/(?:article|articles)/\d+/?$")
_STORM_ARTICLE_ANCHOR_RE = re.compile(
    r"""<a\b(?=[^>]*\bhref=["'](?P<href>[^"']+))[^>]*>(?P<body>.*?)</a>""",
    re.IGNORECASE | re.DOTALL,
)
_STORM_TIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
_SETN_CATEGORY_LABELS = {
    "politics": "政治",
    "society": "社會",
}


@dataclass
class _HtmlListRow:
    url: str
    title: str
    published_at: datetime | None = None
    summary: str | None = None
    listed_category: str | None = None
    parser: str = "html"


class HtmlListSource(NewsSource):
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
            logger.warning("HTML list fetch failed source=%s url=%s error=%s", self.name, self.url, exc)
            return []
        articles = self.parse(payload, source_url=self.url)
        if not articles:
            logger.warning("HTML list empty source=%s url=%s", self.name, self.url)
        articles.sort(key=lambda a: sort_timestamp(a.published_at), reverse=True)
        return articles[: max(int(limit), 1)]

    def parse(self, payload: bytes | str, *, source_url: str | None = None) -> list[NewsArticle]:
        text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
        source_url = source_url or self.url
        rows = self._parse_rows(text, source_url=source_url)
        articles: list[NewsArticle] = []
        for row in rows:
            article = self._row_to_article(row, source_url=source_url)
            if article is None:
                continue
            if not is_recent(article.published_at, max_age_days=self.max_age_days):
                continue
            articles.append(article)
        return _dedupe_articles(articles)

    def _parse_rows(self, text: str, *, source_url: str) -> list[_HtmlListRow]:
        source_id = self.source_id.lower()
        if source_id == "tvbs":
            return _parse_tvbs_json_ld(text)
        if source_id == "udn":
            parser = _UdnStoryListParser(source_url=source_url)
            parser.feed(text)
            return parser.finish()
        if source_id == "setn":
            parser = _SetnNewsListParser(source_url=source_url, category=self.category)
            parser.feed(text)
            return parser.finish()
        if source_id == "storm":
            return _parse_storm_channel(text, source_url=source_url)
        return []

    def _row_to_article(self, row: _HtmlListRow, *, source_url: str) -> NewsArticle | None:
        title = _collapse(row.title)
        original_url = urljoin(source_url, row.url.strip())
        canonical = canonical_url(original_url) or original_url
        if not title or not canonical:
            return None
        if self.path_filter and self.path_filter not in canonical:
            return None

        raw: dict[str, object] = {
            "feed": source_url,
            "original_url": original_url,
            "kind": "html_list",
            "parser": row.parser,
        }
        if row.listed_category:
            raw["listed_category"] = row.listed_category

        return NewsArticle(
            article_id=stable_id(self.source_id, self.category, canonical, title),
            source_id=self.source_id,
            country=self.country,
            category=self.category,
            title=title,
            url=canonical,
            published_at=row.published_at,
            summary=row.summary,
            author_extraction_status=AUTHOR_STATUS_NO_DETAIL_FETCHED,
            author_extraction_method=AUTHOR_METHOD_NONE,
            tags=[row.listed_category] if row.listed_category else [],
            raw=raw,
        )


class _JsonLdScriptParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.scripts: list[str] = []
        self._capture = False
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        if tag == "script" and "ld+json" in attrs_dict.get("type", "").lower():
            self._capture = True
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._capture:
            script = "".join(self._parts).strip()
            if script:
                self.scripts.append(script)
            self._capture = False
            self._parts = []


def _parse_tvbs_json_ld(text: str) -> list[_HtmlListRow]:
    parser = _JsonLdScriptParser()
    parser.feed(text)
    rows: list[_HtmlListRow] = []
    for script in parser.scripts:
        try:
            payload = json.loads(script)
        except json.JSONDecodeError:
            continue
        for node in _walk_json(payload):
            if not isinstance(node, dict) or not _is_schema_type(node, "ListItem"):
                continue
            item = node.get("item")
            if not isinstance(item, dict) or not _is_schema_type(item, "NewsArticle"):
                continue
            url = str(item.get("url") or "").strip()
            title = str(item.get("headline") or item.get("name") or "").strip()
            if not url or not title:
                continue
            rows.append(
                _HtmlListRow(
                    url=url,
                    title=title,
                    published_at=parse_datetime(str(item.get("datePublished") or "")),
                    parser="tvbs_json_ld",
                )
            )
    return rows


def _walk_json(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _is_schema_type(value: dict[str, Any], expected: str) -> bool:
    raw = value.get("@type")
    if isinstance(raw, str):
        return raw.lower() == expected.lower()
    if isinstance(raw, list):
        return any(isinstance(item, str) and item.lower() == expected.lower() for item in raw)
    return False


def _parse_storm_channel(text: str, *, source_url: str) -> list[_HtmlListRow]:
    matches = list(_STORM_ARTICLE_ANCHOR_RE.finditer(text))
    rows: list[_HtmlListRow] = []
    seen: set[str] = set()
    for index, match in enumerate(matches):
        href = _normalized_article_url(match.group("href"), source_url, _STORM_RE)
        if not href or href in seen:
            continue
        title = _html_text(match.group("body"))
        if not title:
            continue
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        nearby = text[match.end() : min(next_start, match.end() + 1000)]
        rows.append(
            _HtmlListRow(
                url=href,
                title=title,
                published_at=_parse_taipei_datetime(_first_storm_time(nearby)),
                parser="storm_channel",
            )
        )
        seen.add(href)
    return rows


def _first_storm_time(value: str) -> str:
    match = _STORM_TIME_RE.search(value)
    return match.group(0) if match else ""


def _html_text(value: str) -> str:
    text = _HTML_COMMENT_RE.sub(" ", value)
    text = _HTML_TAG_RE.sub(" ", text)
    return _collapse(text)


class _UdnStoryListParser(HTMLParser):
    def __init__(self, *, source_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source_url = source_url
        self.rows: list[_HtmlListRow] = []
        self._row: _MutableRow | None = None
        self._depth = 0
        self._field: tuple[str, str] | None = None
        self._href = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        classes = _classes(attrs_dict.get("class", ""))
        if self._row is None and tag == "div" and "story-list__news" in classes:
            self._row = _MutableRow(parser="udn_story_list")
            self._depth = 1
            return
        if self._row is None:
            return
        if tag not in _VOID_TAGS:
            self._depth += 1
        if tag == "a":
            href = _normalized_article_url(attrs_dict.get("href", ""), self.source_url, _UDN_RE)
            if href:
                self._href = href
                self._row.url = self._row.url or href
                title = _collapse(attrs_dict.get("title", ""))
                if title and not self._row.title:
                    self._row.title = title
                self._field = ("title", tag)
            return
        if tag == "p":
            self._field = ("summary", tag)
            return
        if tag == "time":
            self._field = ("time", tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _VOID_TAGS:
            return
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self._row is None or self._field is None:
            return
        text = data.strip()
        if not text:
            return
        field = self._field[0]
        if field == "title":
            self._row.title_parts.append(text)
        elif field == "summary":
            self._row.summary_parts.append(text)
        elif field == "time":
            self._row.time_parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        if self._row is None:
            return
        if self._field and self._field[1] == tag:
            self._field = None
        self._depth -= 1
        if self._depth <= 0:
            self._finish_row()

    def finish(self) -> list[_HtmlListRow]:
        if self._row is not None:
            self._finish_row()
        return self.rows

    def _finish_row(self) -> None:
        assert self._row is not None
        title = self._row.title or _collapse(" ".join(self._row.title_parts))
        if self._row.url and title:
            self.rows.append(
                _HtmlListRow(
                    url=self._row.url,
                    title=title,
                    published_at=_parse_taipei_datetime(_collapse(" ".join(self._row.time_parts))),
                    summary=_collapse(" ".join(self._row.summary_parts)) or None,
                    parser=self._row.parser,
                )
            )
        self._row = None
        self._depth = 0
        self._field = None
        self._href = ""


class _SetnNewsListParser(HTMLParser):
    def __init__(self, *, source_url: str, category: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source_url = source_url
        self.expected_label = _SETN_CATEGORY_LABELS.get(category, category)
        self.rows: list[_HtmlListRow] = []
        self._stack: list[set[str]] = []
        self._row: _MutableRow | None = None
        self._depth = 0
        self._field: tuple[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        classes = _classes(attrs_dict.get("class", ""))
        if tag not in _VOID_TAGS:
            self._stack.append(classes)

        if self._row is None and tag == "div" and "news_list_item" in classes:
            self._row = _MutableRow(parser="setn_news_list")
            self._depth = 1
            return
        if self._row is None:
            return
        if tag not in _VOID_TAGS:
            self._depth += 1
        if tag == "a" and self._inside_class("title_pc"):
            href = _normalized_article_url(attrs_dict.get("href", ""), self.source_url, _SETN_RE)
            if href:
                self._row.url = href
                self._field = ("title", tag)
            return
        if tag == "a" and "tab" in classes:
            self._field = ("category", tag)
            return
        if tag == "div" and "time" in classes:
            self._field = ("time", tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _VOID_TAGS:
            return
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self._row is None or self._field is None:
            return
        text = data.strip()
        if not text:
            return
        field = self._field[0]
        if field == "title":
            self._row.title_parts.append(text)
        elif field == "category":
            self._row.listed_category_parts.append(text)
        elif field == "time":
            self._row.time_parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        if self._row is not None:
            if self._field and self._field[1] == tag:
                self._field = None
            self._depth -= 1
            if self._depth <= 0:
                self._finish_row()
        if self._stack:
            self._stack.pop()

    def finish(self) -> list[_HtmlListRow]:
        if self._row is not None:
            self._finish_row()
        return self.rows

    def _finish_row(self) -> None:
        assert self._row is not None
        title = _collapse(" ".join(self._row.title_parts))
        listed_category = _collapse(" ".join(self._row.listed_category_parts))
        if self._row.url and title and listed_category == self.expected_label:
            self.rows.append(
                _HtmlListRow(
                    url=self._row.url,
                    title=title,
                    published_at=_parse_setn_datetime(_collapse(" ".join(self._row.time_parts))),
                    listed_category=listed_category,
                    parser=self._row.parser,
                )
            )
        self._row = None
        self._depth = 0
        self._field = None

    def _inside_class(self, class_name: str) -> bool:
        return any(class_name in classes for classes in self._stack)


@dataclass
class _MutableRow:
    parser: str
    url: str = ""
    title: str = ""
    title_parts: list[str] = field(default_factory=list)
    summary_parts: list[str] = field(default_factory=list)
    time_parts: list[str] = field(default_factory=list)
    listed_category_parts: list[str] = field(default_factory=list)


def _normalized_article_url(value: str, source_url: str, pattern: re.Pattern[str]) -> str:
    if not value:
        return ""
    url = canonical_url(urljoin(source_url, value.strip()))
    return url if pattern.match(url) else ""


def _classes(value: str) -> set[str]:
    return {part.strip() for part in value.split() if part.strip()}


def _collapse(value: str) -> str:
    return unescape(" ".join(value.split())).strip()


def _parse_taipei_datetime(value: str) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=_TAIPEI)
        except ValueError:
            pass
    return parse_datetime(value)


def _parse_setn_datetime(value: str, *, now: datetime | None = None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    reference = now or datetime.now(_TAIPEI)
    minute_match = re.fullmatch(r"(\d+)\s*分鐘前", text)
    if minute_match:
        return reference - timedelta(minutes=int(minute_match.group(1)))
    hour_match = re.fullmatch(r"(\d+)\s*小時前", text)
    if hour_match:
        return reference - timedelta(hours=int(hour_match.group(1)))
    if text.startswith("昨天"):
        parsed_time = _parse_time_only(text.removeprefix("昨天").strip())
        return (reference - timedelta(days=1)).replace(
            hour=parsed_time[0],
            minute=parsed_time[1],
            second=0,
            microsecond=0,
        ) if parsed_time else None
    for fmt in ("%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=_TAIPEI)
        except ValueError:
            pass
    month_day_match = re.fullmatch(r"(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})", text)
    if month_day_match:
        month, day, hour, minute = [int(part) for part in month_day_match.groups()]
        parsed = reference.replace(month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)
        if parsed > reference + timedelta(days=1):
            parsed = parsed.replace(year=parsed.year - 1)
        return parsed
    return None


def _parse_time_only(value: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", value)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return hour, minute


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
