"""Shared context + result types for the multi-stage analysis pipeline.

``StageContext`` carries provider/model/slot/now_local for each stage
call; ``StageResult`` carries the parsed output, raw text, error string,
and extras telemetry. Stages depend on these dataclasses but not on each
other."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class StageContext:
    """封裝 Stage Context 相關資料與行為。"""
    provider: str
    api_base: str
    api_key: str
    model: str
    slot: str
    now_local: datetime


@dataclass
class StageResult:
    """封裝 Stage Result 相關資料與行為。"""
    name: str
    model: str
    output: Any
    tokens_prompt: int = 0
    tokens_completion: int = 0
    error: str | None = None
    raw_text: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def ok(self) -> bool:
        """執行 ok 方法的主要邏輯。"""
        return self.error is None and self.output is not None
