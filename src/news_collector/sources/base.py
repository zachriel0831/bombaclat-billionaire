"""Abstract base class for every news source.

``NewsSource`` defines a single ``fetch(limit)`` returning ``NewsItem``
rows. Subclasses are registered via the collector's source factory."""

from __future__ import annotations

# 新聞來源抽象基底介面。
from abc import ABC, abstractmethod

from news_collector.models import NewsItem


class NewsSource(ABC):
    """封裝 News Source 相關資料與行為。"""
    name: str

    @abstractmethod
    def fetch(self, limit: int = 20) -> list[NewsItem]:
        """執行 fetch 方法的主要邏輯。"""
        raise NotImplementedError
