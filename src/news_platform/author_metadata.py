"""Author identity and extraction metadata helpers."""

from __future__ import annotations

import hashlib


AUTHOR_STATUS_PRESENT = "present"
AUTHOR_STATUS_NO_AUTHOR_METADATA = "no_author_metadata"
AUTHOR_STATUS_NO_DETAIL_FETCHED = "no_detail_fetched"
AUTHOR_STATUS_PARSER_NOT_SUPPORTED = "parser_not_supported"
AUTHOR_STATUS_PARSE_FAILED = "parse_failed"
AUTHOR_STATUS_LOW_CONFIDENCE = "low_confidence"

AUTHOR_METHOD_RSS_METADATA = "rss_metadata"
AUTHOR_METHOD_SITEMAP_METADATA = "sitemap_metadata"
AUTHOR_METHOD_BYLINE_REGEX = "byline_regex"
AUTHOR_METHOD_ARTICLE_DETAIL = "article_detail"
AUTHOR_METHOD_LEGACY_AUTHORS_JSON = "legacy_authors_json"
AUTHOR_METHOD_NONE = "none"


def author_key(source_id: str, normalized_name: str) -> str:
    """Return a stable source-scoped author identity key."""
    source = (source_id or "").strip().lower()
    name = " ".join((normalized_name or "").strip().split())
    payload = f"news_author:{source}:{name}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
