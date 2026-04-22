"""
Relay Client
向 data-collecting 的 Event Relay 服務送入新聞事件

服務端點: POST http://localhost:18090/events
格式: [{"source":"...","title":"...","url":"...","summary":"...","published_at":"..."}]

如果 relay 服務未啟動，會印警告後跳過（不拋例外）。
"""

import json
import os
import socket
from datetime import datetime, timezone

import requests

RELAY_HOST = os.environ.get("RELAY_HOST", "localhost")
RELAY_PORT = int(os.environ.get("RELAY_PORT", "18090"))
RELAY_URL  = f"http://{RELAY_HOST}:{RELAY_PORT}/events"
TIMEOUT    = 10


# ── 連線探測 ──────────────────────────────────────────────
def is_relay_up() -> bool:
    """快速 TCP 探測，避免 requests 等太久"""
    try:
        with socket.create_connection((RELAY_HOST, RELAY_PORT), timeout=2):
            return True
    except OSError:
        return False


# ── 核心推送 ──────────────────────────────────────────────
def push_events(events: list[dict]) -> dict:
    """
    推送事件清單到 Relay 服務。

    Args:
        events: list of {source, title, url, summary?, published_at?}

    Returns:
        {"ok": True, "inserted": N} or {"ok": False, "error": "..."}
    """
    if not events:
        return {"ok": True, "inserted": 0}

    now_iso = datetime.now(timezone.utc).isoformat()
    for e in events:
        if not e.get("published_at"):
            e["published_at"] = now_iso

    try:
        resp = requests.post(
            RELAY_URL,
            json=events,
            timeout=TIMEOUT,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        try:
            return {"ok": True, **resp.json()}
        except Exception:
            return {"ok": True, "inserted": len(events)}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": f"Relay 服務未啟動 ({RELAY_URL})"}
    except requests.exceptions.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── 便利方法 ──────────────────────────────────────────────
def push_articles(articles: list[dict], source_override: str = "") -> int:
    """
    將爬蟲 article 格式轉換後推送。

    article 格式:
        {title, url, description/summary, published_time/published_at, source}

    Returns:
        成功推送的數量（relay 未啟動時回傳 0，不拋例外）
    """
    events = []
    for a in articles:
        raw_source = source_override or a.get("source", "unknown")
        # 轉換為 snake_case source id: "BBC Business" → "bbc_business"
        source_id = raw_source.lower().replace(" ", "_").replace("-", "_")

        events.append({
            "source":       source_id,
            "title":        a.get("title", "").strip(),
            "url":          a.get("url", "").strip(),
            "summary":      (a.get("description") or a.get("summary", "")).strip(),
            "published_at": a.get("published_time") or a.get("published_at", ""),
        })

    # 過濾掉 title 或 url 為空的項目
    events = [e for e in events if e["title"] and e["url"]]

    if not events:
        print("  [relay] 無有效事件可推送")
        return 0

    result = push_events(events)
    if result["ok"]:
        inserted = result.get("inserted", len(events))
        skipped  = len(events) - inserted
        print(f"  [relay] ✅ 新增 {inserted} 筆 / 重複略過 {skipped} 筆 → MySQL")
        return inserted
    else:
        print(f"  [relay] ⚠️  {result['error']} — 略過 MySQL 寫入")
        return 0
