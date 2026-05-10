"""新聞來源抽象基底。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from news_platform.models import NewsArticle


class NewsSource(ABC):
    name: str

    @abstractmethod
    def fetch(self, limit: int = 20) -> list[NewsArticle]:
        raise NotImplementedError
