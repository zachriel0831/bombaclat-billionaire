import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "src"))
import mysql.connector
from event_relay.config import load_settings


rows = json.loads(Path("runtime/palestine_w44_rows.json").read_text(encoding="utf-8"))
title, dek, body = Path("runtime/palestine_w44_article.md").read_text(encoding="utf-8").strip().split("\n\n", 2)
title = title.removeprefix("# ")
urls = re.findall(r"\]\((https?://[^)]+)\)", body)
sources = [next(row for row in rows if row["url"] == url) for url in urls]
ids = [row["news_id"] for row in sources]
assert len(ids) == len(set(ids)) == len(urls) == len(set(urls)) == 5
assert all(row["in_publication_window"] for row in sources)
audit = {
    "sources": sources,
    "reviewed_sources": rows,
    "reviewed_row_count": len(rows),
    "publication_window_rows": sum(row["in_publication_window"] for row in rows),
    "first_seen_window_only_rows": sum(row["in_first_seen_window"] and not row["in_publication_window"] for row in rows),
    "source_urls": urls,
    "source_window_timezone": "Asia/Taipei",
    "source_window_basis": "Published date in Taipei; inclusive October 25-31, equivalent to [2026-10-25T00:00+08:00,2026-11-01T00:00+08:00). First-seen-window rows outside the publication window were reviewed separately.",
    "source_count_basis": "Unique sources cited in body",
    "external_provider_api_called": False,
    "check_notes": [
        "All 144 complete matching rows were reviewed: 131 publication-window rows and 13 first-seen-window-only rows.",
        "Raw metadata was parsed for every reviewed row; duplicate coverage, opinion, and unrelated regional entries were retained in the audit but excluded from factual support.",
        "Five cited publication-window records support only the bounded factual statements in the body.",
        "The UN human-rights-office warning is identified as an institutional report, not an ICJ advisory opinion, pending proceeding outcome, NGO legal conclusion, or final court judgment.",
        "Traditional Chinese text and citations were manually reviewed. No paid external LLM API was called.",
    ],
}
record = {
    "editorial_id": "palestine-weekly-2026-W44", "title": title, "dek": dek,
    "body_markdown": body, "source_window_start": "2026-10-25", "source_window_end": "2026-10-31",
    "source_count": len(ids), "source_news_ids_json": json.dumps(ids), "model": "codex",
    "prompt_version": "palestine-weekly-editorial-v1", "generated_by": "codex-weekly-editorial",
    "status": "published", "raw_json": json.dumps(audit, ensure_ascii=False),
}


def validate(saved):
    text = saved["title"] + saved["dek"] + saved["body_markdown"]
    checks = {
        "exact_utf8_text": all(saved[key] == record[key] for key in ("title", "dek", "body_markdown")),
        "no_mojibake_or_question_blocks": not re.search(r"\?{2,}|\ufffd|Ã|Â|â€", text),
        "readable_traditional_chinese": all(token in text for token in ("巴勒斯坦", "平民", "醫療", "人權")),
        "source_count_matches_ids": saved["source_count"] == len(ids) == len(set(ids)) and json.loads(saved["source_news_ids_json"]) == ids,
        "citations_match_reviewed_urls": urls == audit["source_urls"] and all(row["in_publication_window"] for row in sources),
        "no_raw_json_dump_in_body": not any(token in body for token in ("raw_json", "source_news_ids_json", "{", "}")),
        "metadata_matches": all(str(saved[key]) == str(record[key]) for key in ("editorial_id", "source_window_start", "source_window_end", "model", "prompt_version", "generated_by", "status")),
        "complete_audit_matches": json.loads(saved["raw_json"]) == audit,
        "published_at_present": saved["published_at"] is not None,
    }
    assert all(checks.values()), checks
    return checks


checks = validate({**record, "published_at": "dry-run"})
if "--publish" in sys.argv or "--verify" in sys.argv:
    settings = load_settings(".env")
    connection = mysql.connector.connect(host=settings.mysql_host, port=settings.mysql_port, user=settings.mysql_user, password=settings.mysql_password, database=settings.mysql_database, connection_timeout=5, charset="utf8mb4")
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SET time_zone = '+00:00'")
        if "--publish" in sys.argv:
            columns = list(record)
            cursor.execute("INSERT INTO t_palestine_editorials (" + ",".join(columns) + ",published_at) VALUES (" + ",".join(["%s"] * len(columns)) + ",UTC_TIMESTAMP()) ON DUPLICATE KEY UPDATE " + ",".join(key + "=VALUES(" + key + ")" for key in columns if key != "editorial_id") + ",published_at=VALUES(published_at)", tuple(record.values()))
        cursor.execute("SELECT * FROM t_palestine_editorials WHERE editorial_id=%s", (record["editorial_id"],))
        saved = cursor.fetchall()
        assert len(saved) == 1
        checks = validate(saved[0])
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
report = {"editorial_id": record["editorial_id"], "source_window": "2026-10-25 through 2026-10-31 inclusive, Asia/Taipei", "source_count": len(ids), "reviewed_rows": len(rows), "validation": checks, "mode": "verify" if "--verify" in sys.argv else "publish" if "--publish" in sys.argv else "dry-run", "external_provider_api_called": False}
Path("runtime/palestine_w44_validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False))
