from __future__ import annotations

# 新聞來源抽象基底介面。
from abc import ABC, abstractmethod

from news_collector.models import NewsItem


class NewsSource(ABC):
    name: str

    @abstractmethod
    def fetch(self, limit: int = 20) -> list[NewsItem]:
        raise NotImplementedError
