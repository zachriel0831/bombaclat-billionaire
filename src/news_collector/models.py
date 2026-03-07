from __future__ import annotations

# 新聞資料模型定義。
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any


@dataclass
class NewsItem:
    id: str
    source: str
    title: str
    url: str
    published_at: datetime | None
    summary: str | None
    tags: list[str]
    raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["published_at"] = self.published_at.isoformat() if self.published_at else None
        return data
