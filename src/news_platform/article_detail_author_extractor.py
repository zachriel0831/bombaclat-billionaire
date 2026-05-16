"""Extract reporter names from already-known article detail pages.

This module is intentionally narrow: it reads public article HTML only to enrich
missing byline metadata. It does not extract or persist article body content.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Iterable

from news_platform.author_extractor import extract_authors_from_text, normalize_authors
from news_platform.author_metadata import (
    AUTHOR_METHOD_ARTICLE_DETAIL,
    AUTHOR_STATUS_LOW_CONFIDENCE,
    AUTHOR_STATUS_NO_AUTHOR_METADATA,
    AUTHOR_STATUS_PRESENT,
)


_AUTHOR_META_KEYS = {
    "author",
    "article:author",
    "byl",
    "creator",
    "dc.creator",
    "dcterms.creator",
    "parsely-author",
    "sailthru.author",
}
_JSON_AUTHOR_KEYS = {"author", "creator"}
_VISIBLE_LOCATION_MARKERS = (
    "台北",
    "臺北",
    "新北",
    "桃園",
    "台中",
    "臺中",
    "台南",
    "臺南",
    "高雄",
    "基隆",
    "新竹",
    "苗栗",
    "彰化",
    "南投",
    "雲林",
    "嘉義",
    "屏東",
    "宜蘭",
    "花蓮",
    "台東",
    "臺東",
    "澎湖",
    "金門",
    "連江",
    "華盛頓",
    "東京",
    "北京",
    "上海",
)
_VISIBLE_LOCATION_PATTERN = "|".join(
    re.escape(marker) for marker in sorted(_VISIBLE_LOCATION_MARKERS, key=len, reverse=True)
)
_VISIBLE_MARKER_RE = re.compile(
    r"(?:中央社)?(?:記者|记者)\s*"
    rf"[\u4e00-\u9fffA-Za-z\u00b7\u2027\u30fb\uff0e. ]{{2,24}}?"
    rf"(?=\s*(?:[／/]|{_VISIBLE_LOCATION_PATTERN}))|"
    r"(?:^|[\s〔（(【])(?:文|撰文|採訪|整理|作者)\s*[／/:：]"
)
_BODY_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class ArticleDetailAuthorResult:
    """Result of one article-detail byline extraction attempt."""

    authors: list[str]
    status: str
    method: str
    confidence: float | None
    raw_text: str | None


class _ArticleHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta_values: list[str] = []
        self.json_ld_values: list[str] = []
        self.visible_parts: list[str] = []
        self._script_type: str | None = None
        self._script_parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        if tag in {"style", "noscript", "svg"}:
            self._skip_depth += 1
            return
        if tag == "script":
            self._script_type = attrs_dict.get("type", "").lower()
            self._script_parts = []
            self._skip_depth += 1
            return
        if tag == "meta":
            key = (
                attrs_dict.get("name")
                or attrs_dict.get("property")
                or attrs_dict.get("itemprop")
                or ""
            ).strip().lower()
            value = attrs_dict.get("content", "").strip()
            if key in _AUTHOR_META_KEYS and value:
                self.meta_values.append(value)

    def handle_data(self, data: str) -> None:
        if self._script_type:
            self._script_parts.append(data)
            return
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self.visible_parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            if self._script_type == "application/ld+json":
                value = "".join(self._script_parts).strip()
                if value:
                    self.json_ld_values.append(value)
            self._script_type = None
            self._script_parts = []
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag in {"style", "noscript", "svg"}:
            self._skip_depth = max(0, self._skip_depth - 1)


class ArticleDetailAuthorExtractor:
    """Conservative author-name extractor for public article detail HTML."""

    def extract(self, payload: bytes | str, *, source_id: str = "", url: str = "") -> ArticleDetailAuthorResult:
        text = _decode_payload(payload)
        parser = _ArticleHTMLParser()
        parser.feed(text)

        candidates = [
            (self._json_ld_author_values(parser.json_ld_values), 0.95, True),
            (parser.meta_values, 0.95, True),
            (self._visible_byline_values(parser.visible_parts), 0.9, False),
        ]
        saw_raw_value = False
        first_raw_text: str | None = None

        for values, confidence, allow_normalize in candidates:
            raw_values = [_clean_raw(value) for value in values if _clean_raw(value)]
            if raw_values and first_raw_text is None:
                first_raw_text = " | ".join(raw_values)[:500]
            if raw_values:
                saw_raw_value = True
            authors = normalize_authors(raw_values) if allow_normalize else []
            for raw_value in raw_values:
                extracted = extract_authors_from_text(raw_value)
                if extracted:
                    authors = extracted
                    break
            if authors:
                return ArticleDetailAuthorResult(
                    authors=authors,
                    status=AUTHOR_STATUS_PRESENT,
                    method=AUTHOR_METHOD_ARTICLE_DETAIL,
                    confidence=confidence,
                    raw_text=" | ".join(raw_values)[:500],
                )

        return ArticleDetailAuthorResult(
            authors=[],
            status=AUTHOR_STATUS_LOW_CONFIDENCE if saw_raw_value else AUTHOR_STATUS_NO_AUTHOR_METADATA,
            method=AUTHOR_METHOD_ARTICLE_DETAIL,
            confidence=0.0 if saw_raw_value else None,
            raw_text=first_raw_text,
        )

    @staticmethod
    def _json_ld_author_values(values: Iterable[str]) -> list[str]:
        output: list[str] = []
        for value in values:
            try:
                payload = json.loads(html.unescape(value).strip())
            except json.JSONDecodeError:
                continue
            output.extend(_author_values_from_json(payload))
        return _unique(output)

    @staticmethod
    def _visible_byline_values(parts: list[str]) -> list[str]:
        plain = _BODY_SPACE_RE.sub(" ", " ".join(parts)).strip()
        if not plain:
            return []
        output: list[str] = []
        for match in _VISIBLE_MARKER_RE.finditer(plain[:12000]):
            start = max(0, match.start() - 16)
            end = min(len(plain), match.end() + 120)
            output.append(plain[start:end])
            if len(output) >= 5:
                break
        return output


def _author_values_from_json(value: Any) -> list[str]:
    if isinstance(value, list):
        output: list[str] = []
        for item in value:
            if isinstance(item, (dict, list)):
                output.extend(_author_values_from_json(item))
        return output
    if not isinstance(value, dict):
        return []

    output: list[str] = []
    for key, nested in value.items():
        normalized_key = str(key).lower()
        if normalized_key in _JSON_AUTHOR_KEYS:
            output.extend(_name_values(nested))
        elif normalized_key == "@graph":
            output.extend(_author_values_from_json(nested))
        elif isinstance(nested, (dict, list)):
            output.extend(_author_values_from_json(nested))
    return output


def _name_values(value: Any) -> list[str]:
    if isinstance(value, list):
        output: list[str] = []
        for item in value:
            output.extend(_name_values(item))
        return output
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        if "name" in value:
            return _name_values(value["name"])
        if "@id" in value:
            return _name_values(value["@id"])
    return []


def _decode_payload(payload: bytes | str) -> str:
    if isinstance(payload, str):
        return payload
    for encoding in ("utf-8", "big5", "cp950"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


def _clean_raw(value: str) -> str:
    return _BODY_SPACE_RE.sub(" ", html.unescape(str(value))).strip()


def _unique(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        cleaned = _clean_raw(value)
        if cleaned and cleaned not in output:
            output.append(cleaned)
    return output
