"""
Query Recent Events from MySQL
從 t_relay_events 查詢最近 N 小時的新聞與股價快照

Usage:
    python src/query_recent_events.py            # 最近 3 小時
    python src/query_recent_events.py --hours 6  # 最近 6 小時
    python src/query_recent_events.py --type news    # 只撈新聞
    python src/query_recent_events.py --type stocks  # 只撈股價
    python src/query_recent_events.py --type all     # 全部（預設）

輸出: JSON 到 stdout
依賴: mysql-connector-python（已在 pyproject.toml）
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# 讀取 .env（與 relay service 相同的設定方式）
def _load_env(env_file: str = ".env") -> None:
    p = Path(env_file)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# ── MySQL 連線設定（從環境變數讀取）──────────────────────
def _get_db_config() -> dict:
    return {
        "host":             os.environ.get("RELAY_MYSQL_HOST",     "127.0.0.1"),
        "port":             int(os.environ.get("RELAY_MYSQL_PORT", "3306")),
        "user":             os.environ.get("RELAY_MYSQL_USER",     "root"),
        "password":         os.environ.get("RELAY_MYSQL_PASSWORD", "root"),
        "database":         os.environ.get("RELAY_MYSQL_DATABASE", "news_relay"),
        "connection_timeout": int(os.environ.get("RELAY_MYSQL_CONNECT_TIMEOUT", "5")),
        "charset":          "utf8mb4",
    }


TABLE = os.environ.get("RELAY_MYSQL_EVENT_TABLE", "t_relay_events")


def query_events(hours: int = 3, event_type: str = "all") -> dict:
    """
    查詢最近 hours 小時的事件。

    event_type:
        "news"   → source NOT LIKE 'yfinance_%'
        "stocks" → source LIKE 'yfinance_%'
        "all"    → 全部
    """
    try:
        import mysql.connector  # type: ignore
    except ImportError:
        return {
            "error": "mysql-connector-python 未安裝，執行: pip install -e .",
            "news": [], "stocks": [],
        }

    where_type = ""
    if event_type == "news":
        where_type = "AND source NOT LIKE 'yfinance_%'"
    elif event_type == "stocks":
        where_type = "AND source LIKE 'yfinance_%'"

    sql = f"""
        SELECT source, title, url, summary, published_at, created_at
        FROM   {TABLE}
        WHERE  created_at >= NOW() - INTERVAL %s HOUR
        {where_type}
        ORDER  BY source, created_at DESC
    """

    try:
        conn   = mysql.connector.connect(**_get_db_config())
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, (hours,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
    except mysql.connector.Error as e:
        return {"error": str(e), "news": [], "stocks": []}
    except Exception as e:
        return {"error": str(e), "news": [], "stocks": []}

    # 分類
    news_rows   = [r for r in rows if not str(r.get("source", "")).startswith("yfinance_")]
    stocks_rows = [r for r in rows if str(r.get("source", "")).startswith("yfinance_")]

    # 股票快照：每個 symbol URL 只取最新一筆
    seen = set()
    latest_stocks = []
    for r in stocks_rows:
        key = str(r.get("url", ""))
        if key not in seen:
            seen.add(key)
            try:
                r["quote"] = json.loads(r["summary"]) if r.get("summary") else {}
            except Exception:
                r["quote"] = {}
            latest_stocks.append(r)

    # datetime 物件轉字串
    def _dt(v):
        return v.isoformat() if isinstance(v, datetime) else str(v) if v is not None else None

    for r in news_rows + latest_stocks:
        for key in ("published_at", "created_at"):
            r[key] = _dt(r.get(key))

    return {
        "queried_at":   datetime.now(timezone.utc).isoformat(),
        "hours":        hours,
        "news_count":   len(news_rows),
        "stocks_count": len(latest_stocks),
        "news":         news_rows,
        "stocks":       latest_stocks,
    }


def main():
    # 自動尋找 .env（從 src/ 往上找到專案根目錄）
    script_dir = Path(__file__).resolve().parent
    env_path   = script_dir.parent / ".env"
    _load_env(str(env_path))

    parser = argparse.ArgumentParser(description="Query recent relay events from MySQL")
    parser.add_argument("--hours", type=int, default=3, help="過去幾小時（預設 3）")
    parser.add_argument("--type",  choices=["all", "news", "stocks"], default="all")
    args = parser.parse_args()

    result = query_events(args.hours, args.type)

    if result.get("error"):
        print(f"[ERROR] {result['error']}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
