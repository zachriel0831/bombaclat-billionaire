"""新聞標題關鍵字抽取 — jieba TF-IDF + TW 停用詞。

設計重點：
- 懶載入 jieba：避免 import news_platform 時就花 1s 初始化
- 停用詞合併 jieba 預設與本套件 ``data/stopwords_tw.txt``
- 標題太短或語料缺失時回 []，呼叫端要能容忍 0 筆
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from threading import Lock


logger = logging.getLogger(__name__)


_STOPWORDS_PATH = Path(__file__).parent / "data" / "stopwords_tw.txt"

# 不要直接抽出去做關鍵字的字元樣式：純標點、純空白、單字數字（保留多位數字以維持事件 hook）。
_PUNCT_ONLY_RE = re.compile(r"^[\W_]+$", re.UNICODE)


class KeywordExtractor:
    """jieba TF-IDF 為核心的關鍵字抽取器。

    第一次呼叫 ``extract`` 時才初始化 jieba 與停用詞表；之後的呼叫共用同一份。
    """

    def __init__(self, *, top_k: int = 5, min_keyword_length: int = 2) -> None:
        self.top_k = max(1, int(top_k))
        self.min_keyword_length = max(1, int(min_keyword_length))
        self._jieba_analyse = None
        self._stopwords: set[str] = set()
        self._init_lock = Lock()
        self._initialized = False

    def extract(self, text: str | None, *, top_k: int | None = None) -> list[tuple[str, float]]:
        """抽取 top_k 個關鍵字 + 對應分數（TF-IDF）。文字為空回 []。"""
        if not text:
            return []
        cleaned = text.strip()
        if not cleaned:
            return []

        self._ensure_initialized()
        analyse = self._jieba_analyse
        assert analyse is not None  # noqa: S101 — 已被 _ensure_initialized 保證

        k = max(1, int(top_k)) if top_k is not None else self.top_k
        # 多抽幾個再過濾停用詞，確保最後仍有 k 個輸出（除非標題本身就很短）。
        candidates = analyse.extract_tags(cleaned, topK=k * 3, withWeight=True)
        results: list[tuple[str, float]] = []
        for kw, score in candidates:
            kw = kw.strip()
            if not kw:
                continue
            if len(kw) < self.min_keyword_length:
                continue
            if kw in self._stopwords:
                continue
            if _PUNCT_ONLY_RE.match(kw):
                continue
            results.append((kw, float(score)))
            if len(results) >= k:
                break
        return results

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            try:
                import jieba.analyse as analyse  # type: ignore
            except Exception as exc:
                raise RuntimeError(
                    "jieba is required for keyword extraction. Run: pip install jieba"
                ) from exc
            self._jieba_analyse = analyse
            self._stopwords = _load_stopwords()
            try:
                # jieba 的 TF-IDF 在計分時會排除停用詞，餵進去能讓低權重雜詞早點被排掉。
                analyse.set_stop_words(str(_STOPWORDS_PATH))
            except Exception as exc:  # pragma: no cover - 防禦
                logger.warning("set_stop_words failed: %s", exc)
            self._initialized = True


def _load_stopwords() -> set[str]:
    if not _STOPWORDS_PATH.exists():
        return set()
    words: set[str] = set()
    for line in _STOPWORDS_PATH.read_text(encoding="utf-8").splitlines():
        word = line.strip()
        if word and not word.startswith("#"):
            words.add(word)
    return words
