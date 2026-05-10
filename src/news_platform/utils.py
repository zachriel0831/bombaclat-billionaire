"""共用工具：時間解析、穩定 ID、URL 正規化、HTML 摘要清理。"""

from __future__ import annotations

import email.utils
import hashlib
import html
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


# 已知會被加在 URL 上做點擊追蹤的參數；canonical 化時一律剝除以提升去重命中率。
_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAM_NAMES = frozenset(
    {
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "ref_src",
        "ref_url",
        "ref",
        "spm",
        "igshid",
        "_ga",
        "yclid",
        "msclkid",
        "from",
    }
)

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None

    if text.isdigit() and len(text) == 14:
        return datetime.strptime(text, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)

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


def stable_id(*parts: str) -> str:
    joined = "||".join(p.strip() for p in parts if p and p.strip())
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:20]


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def sort_timestamp(value: datetime | None) -> float:
    if value is None:
        return 0.0
    dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def canonical_url(url: str) -> str:
    """正規化 URL：去 fragment、剝追蹤參數、scheme/host 小寫、保留 query 順序穩定。

    用於 dedupe 鍵與 stable_id；不改變語意路徑。
    """
    if not url:
        return ""
    text = url.strip()
    if not text:
        return ""
    try:
        parts = urlsplit(text)
    except ValueError:
        return text

    if not parts.scheme:
        return text

    kept_query: list[tuple[str, str]] = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        lower = key.lower()
        if lower in _TRACKING_PARAM_NAMES:
            continue
        if any(lower.startswith(prefix) for prefix in _TRACKING_PARAM_PREFIXES):
            continue
        kept_query.append((key, value))

    netloc = parts.netloc.lower()
    scheme = parts.scheme.lower()
    new_query = urlencode(kept_query, doseq=True)
    return urlunsplit((scheme, netloc, parts.path, new_query, ""))


def clean_summary(value: str | None, *, max_chars: int = 1200) -> str | None:
    """RSS description 常含 HTML / entity / 換行雜訊；統一壓平成純文字並截長。"""
    if value is None:
        return None
    text = html.unescape(value)
    text = _HTML_TAG_RE.sub(" ", text)
    text = " ".join(text.split())
    if not text:
        return None
    if len(text) > max_chars:
        text = text[:max_chars]
    return text


def is_recent(value: datetime | None, *, max_age_days: int, now: datetime | None = None) -> bool:
    """判斷 published_at 是否落在最近 N 天內。published_at 為 None 視為通過（不過濾）。"""
    if value is None:
        return True
    if max_age_days <= 0:
        return True
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    target = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return target >= reference - timedelta(days=max_age_days)
