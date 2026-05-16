"""Reporter/author extraction helpers for news-platform article feeds."""

from __future__ import annotations

import html
import re
from typing import Iterable


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PAREN_NAME_RE = re.compile(r"\((?P<name>[^()]+)\)")
_LOCATION_MARKERS = (
    "\u53f0\u5317",
    "\u81fa\u5317",
    "\u65b0\u5317",
    "\u6843\u5712",
    "\u53f0\u4e2d",
    "\u81fa\u4e2d",
    "\u53f0\u5357",
    "\u81fa\u5357",
    "\u9ad8\u96c4",
    "\u57fa\u9686",
    "\u65b0\u7af9",
    "\u82d7\u6817",
    "\u5f70\u5316",
    "\u5357\u6295",
    "\u96f2\u6797",
    "\u5609\u7fa9",
    "\u5c4f\u6771",
    "\u5b9c\u862d",
    "\u82b1\u84ee",
    "\u53f0\u6771",
    "\u81fa\u6771",
    "\u6f8e\u6e56",
    "\u91d1\u9580",
    "\u9023\u6c5f",
    "\u83ef\u76db\u9813",
    "\u6771\u4eac",
    "\u5317\u4eac",
    "\u4e0a\u6d77",
)
_LOCATION_PATTERN = "|".join(
    re.escape(marker) for marker in sorted(_LOCATION_MARKERS, key=len, reverse=True)
)
_REPORTER_NAME_CHARS = r"[\u4e00-\u9fffA-Za-z\u00b7\u2027\u30fb\uff0e. ]"

_REPORTER_RE = re.compile(
    r"(?:\u4e2d\u592e\u793e)?(?:\u8a18\u8005|\u8bb0\u8005)\s*"
    rf"(?P<body>{_REPORTER_NAME_CHARS}{{2,24}}?)(?=\s*(?:[\uff0f/]|{_LOCATION_PATTERN}))"
)
_BYLINE_RE = re.compile(
    r"(?:^|[\s\u3014\uff08(【])"
    r"(?:\u6587|\u64b0\u6587|\u63a1\u8a2a|\u6574\u7406|\u4f5c\u8005)"
    r"\s*[\uff0f/:：]\s*"
    r"(?P<body>[\u4e00-\u9fffA-Za-z\u00b7\u2027\u30fb\uff0e. ]{2,60})"
)

_SEPARATORS_RE = re.compile(r"[\uff0f/|｜,，;；\n\r\t]")
_ROLE_PREFIX_RE = re.compile(
    r"^(?:\u4e2d\u592e\u793e)?(?:\u8a18\u8005|\u8bb0\u8005|by|author|"
    r"\u5be6\u7fd2\u7de8\u8f2f|\u5b9e\u4e60\u7f16\u8f91|\u8cac\u4efb\u7de8\u8f2f|"
    r"\u8d23\u4efb\u7f16\u8f91|\u7de8\u8f2f|\u7f16\u8f91|"
    r"\u6587|\u64b0\u6587|\u63a1\u8a2a|\u6574\u7406|\u4f5c\u8005)\s*[:：]?\s*",
    re.IGNORECASE,
)
_ROLE_SUFFIXES = (
    "\u7d9c\u5408\u5831\u5c0e",
    "\u7efc\u5408\u62a5\u5bfc",
    "\u7d9c\u5408",
    "\u7efc\u5408",
    "\u7ffb\u651d",
    "\u7ffb",
    "\u651d\u5f71",
    "\u5831\u5c0e",
    "\u62a5\u5bfc",
    "\u96fb",
    "\u7535",
    "\u6307\u51fa",
    "\u651d",
    "\u6574\u7406",
)
_NON_AUTHOR_EXACT_NAMES = {
    "\u5206\u6790",
    "\u4e0d\u5e78\u5931\u806f",
    "\u4e0d\u884c",
    "\u6703\u7684",
    "\u6703\u4e0a",
    "\u64da\u4e86\u89e3",
    "\u622a\u81f3\u76ee\u524d\u70ba\u6b62",
    "\u5c31\u662f",
    "\u56e0\u70ba",
    "\u554f\u4ed6",
}
_NON_AUTHOR_PHRASE_TOKENS = (
    "\u8a18\u8005\u6703",
    "\u6703\u8868\u793a",
    "\u6703\u5f37\u8abf",
    "\u6703\u8b49\u5be6",
    "\u6703\u50c5\u8868\u793a",
    "\u6703\u4e2d",
    "\u6703\u6642",
    "\u8868\u793a",
    "\u6307\u51fa",
    "\u5f37\u8abf",
    "\u547c\u7c72",
    "\u78ba\u8a8d",
    "\u5beb\u660e",
    "\u5931\u806f",
    "\u4e86\u89e3",
    "\u76ee\u524d",
    "\u9700\u8981",
    "\u771f\u76f8",
    "\u6230\u722d",
    "\u63a8\u52d5",
    "\u63d0\u5831",
    "\u8a02\u5b9a",
    "\u5c07\u65bc",
    "\u82e5\u78ba\u8a8d",
    "\u627e\u51fa",
    "\u6536\u5230",
    "\u81ea\u5df1\u5728",
    "\u8c48\u6599",
    "\u4e00\u518d",
    "\u751a\u81f3",
    "\u660e\u77e5",
    "\u537b\u4e0d",
)
_NON_AUTHOR_LEADING_TOKENS = (
    "\u6703",
    "\u5176",
    "\u4ed6",
    "\u5979",
    "\u5c07",
    "\u82e5",
    "\u4e26",
    "\u4f46",
    "\u5728",
    "\u4e0d",
    "\u5df2",
    "\u7d93",
    "\u770b\u4f3c",
    "\u6536\u5230",
    "\u81ea\u5df1",
    "\u751a\u81f3",
    "\u537b",
)
_PUBLICATION_NAMES = {
    "\u4e2d\u592e\u793e",
    "\u81ea\u7531\u6642\u5831",
    "\u81ea\u7531\u6642\u5831\u96fb\u5b50\u5831",
    "\u81ea\u7531\u96fb\u5b50\u5831",
    "ETtoday",
    "ETtoday\u65b0\u805e\u96f2",
    "TVBS",
    "TVBS\u65b0\u805e\u7db2",
    "Newtalk",
    "Newtalk\u65b0\u805e",
    "\u98a8\u50b3\u5a92",
    "\u5de5\u5546\u6642\u5831",
    "\u516c\u8996\u65b0\u805e\u7db2",
    "\u4e2d\u6642\u65b0\u805e\u7db2",
    "\u806f\u5408\u65b0\u805e\u7db2",
    "Yahoo\u65b0\u805e",
}


def normalize_authors(values: Iterable[str | None]) -> list[str]:
    """Return unique, cleaned author names from explicit feed metadata."""
    authors: list[str] = []
    for value in values:
        for candidate in _candidate_parts(value):
            cleaned = _clean_author(candidate)
            if cleaned and cleaned not in authors:
                authors.append(cleaned)
    return authors


def extract_authors_from_text(text: str | None) -> list[str]:
    """Extract high-confidence reporter names from common Taiwan byline text."""
    if not text:
        return []
    plain = _plain_text(text)[:500]
    authors: list[str] = []
    for pattern in (_REPORTER_RE, _BYLINE_RE):
        for match in pattern.finditer(plain):
            cleaned = _clean_author(match.group("body"))
            if cleaned and cleaned not in authors:
                authors.append(cleaned)
    return authors


def _candidate_parts(value: str | None) -> list[str]:
    if not value:
        return []
    text = _plain_text(value)
    if not text:
        return []

    match = _PAREN_NAME_RE.search(text)
    if match:
        text = match.group("name")

    reporter_authors = extract_authors_from_text(text)
    if reporter_authors:
        return reporter_authors

    return [part.strip() for part in _SEPARATORS_RE.split(text) if part.strip()]


def _clean_author(value: str | None) -> str | None:
    if not value:
        return None
    text = _plain_text(value)
    text = re.sub(r"^\d+[-_]\s*", "", text).strip()
    text = _ROLE_PREFIX_RE.sub("", text).strip()
    text = re.sub(r"\d+.*$", "", text).strip()
    text = _trim_after_location(text)
    text = _SEPARATORS_RE.split(text, maxsplit=1)[0].strip()
    for suffix in _ROLE_SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    text = text.strip(" -_()（）[]【】「」'\"")

    if not text or _EMAIL_RE.match(text) or "@" in text or "http" in text.lower():
        return None
    if re.fullmatch(r"(?:www\.)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}.*", text):
        return None
    if text in _PUBLICATION_NAMES:
        return None
    if text in _NON_AUTHOR_EXACT_NAMES:
        return None
    if any(text.startswith(token) for token in _NON_AUTHOR_LEADING_TOKENS):
        return None
    if any(token in text for token in _NON_AUTHOR_PHRASE_TOKENS):
        return None
    if any(token in text for token in ("\u65b0\u805e", "\u5831", "\u96fb\u8996", "\u516c\u53f8")):
        return None

    chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
    if chinese_chars:
        if not (2 <= len(chinese_chars) <= 6):
            return None
        return "".join(chinese_chars)

    if re.fullmatch(r"[A-Za-z][A-Za-z .'\-]{1,60}", text):
        return " ".join(text.split())
    return None


def _trim_after_location(text: str) -> str:
    for marker in sorted(_LOCATION_MARKERS, key=len, reverse=True):
        index = text.find(marker)
        if index >= 2:
            return text[:index].strip()
    return text


def _plain_text(value: str) -> str:
    text = html.unescape(value)
    text = _HTML_TAG_RE.sub(" ", text)
    return " ".join(text.split())
