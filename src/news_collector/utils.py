from __future__ import annotations

# 共用工具：時間解析、穩定 ID 與排序鍵。
from datetime import datetime, timezone
import email.utils
import hashlib


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    text = value.strip()
    if not text:
        return None

    if text.isdigit() and len(text) == 14:
        # Support compact UTC timestamps such as 20260305123045.
        dt = datetime.strptime(text, "%Y%m%d%H%M%S")
        return dt.replace(tzinfo=timezone.utc)

    try:
        dt = email.utils.parsedate_to_datetime(text)
        if dt is not None:
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        pass

    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def sort_timestamp(value: datetime | None) -> float:
    if value is None:
        return 0.0
    dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def stable_id(*parts: str) -> str:
    joined = "||".join(part.strip() for part in parts if part and part.strip())
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:20]


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag
