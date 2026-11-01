import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "src"))
import mysql.connector
from event_relay.config import load_settings

window_start, window_end = "2026-10-25", "2026-11-01"
settings = load_settings(".env")
connection = mysql.connector.connect(
    host=settings.mysql_host, port=settings.mysql_port, user=settings.mysql_user,
    password=settings.mysql_password, database=settings.mysql_database,
    connection_timeout=5, charset="utf8mb4",
)
try:
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        "SELECT news_id,title,source_id,source_name,url,summary,published_at,"
        "first_seen_at,raw_json FROM t_palestine_news_items "
        "WHERE language='en' AND topic='free_palestine' ORDER BY first_seen_at,news_id"
    )
    rows = []
    for row in cursor.fetchall():
        try:
            published = datetime.fromisoformat(str(row["published_at"]).replace("Z", "+00:00"))
            taipei_day = published.astimezone(timezone(timedelta(hours=8))).date().isoformat()
        except (ValueError, TypeError):
            taipei_day = ""
        row["published_taipei_date"] = taipei_day
        row["in_publication_window"] = window_start <= taipei_day < window_end
        row["in_first_seen_window"] = window_start <= str(row["first_seen_at"])[:10] < window_end
        if row["in_publication_window"] or row["in_first_seen_window"]:
            try:
                row["raw_json"] = json.loads(row["raw_json"] or "{}")
            except json.JSONDecodeError:
                row["raw_json_parse_error"] = True
            rows.append(row)
    Path("runtime/palestine_w44_rows.json").write_text(
        json.dumps(rows, ensure_ascii=False, default=str, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "reviewed_rows": len(rows),
        "publication_window_rows": sum(row["in_publication_window"] for row in rows),
        "first_seen_window_only_rows": sum(row["in_first_seen_window"] and not row["in_publication_window"] for row in rows),
        "raw_metadata_parse_errors": sum(bool(row.get("raw_json_parse_error")) for row in rows),
    }))
finally:
    connection.close()
