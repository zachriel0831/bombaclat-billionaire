"""新聞平台資料模型。"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any

from news_platform.author_metadata import (
    AUTHOR_METHOD_NONE,
    AUTHOR_STATUS_PARSER_NOT_SUPPORTED,
)


@dataclass
class NewsArticle:
    """單篇新聞文章 — pipeline 與 store 之間的傳遞單位。"""

    article_id: str
    source_id: str
    country: str
    category: str
    title: str
    url: str
    published_at: datetime | None
    summary: str | None
    authors: list[str] = field(default_factory=list)
    author_extraction_status: str = AUTHOR_STATUS_PARSER_NOT_SUPPORTED
    author_extraction_method: str = AUTHOR_METHOD_NONE
    author_extraction_confidence: float | None = None
    author_raw_text: str | None = None
    author_extracted_at: datetime | None = None
    tags: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["published_at"] = (
            self.published_at.isoformat() if self.published_at else None
        )
        data["author_extracted_at"] = (
            self.author_extracted_at.isoformat() if self.author_extracted_at else None
        )
        return data


@dataclass
class PublicRecord:
    """Structured official fact stored outside the article table."""

    record_id: str
    source_id: str
    record_type: str
    country: str
    title: str
    url: str | None = None
    occurred_at: datetime | None = None
    category: str | None = None
    region: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["occurred_at"] = (
            self.occurred_at.isoformat() if self.occurred_at else None
        )
        return data
