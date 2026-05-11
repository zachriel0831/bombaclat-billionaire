"""新聞平台資料模型。"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any


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
    tags: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["published_at"] = (
            self.published_at.isoformat() if self.published_at else None
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
