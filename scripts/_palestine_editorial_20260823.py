from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

from event_relay.config import load_settings
from event_relay.service import MySqlEventStore


WINDOW_START = "2026-08-16 00:00:00"
WINDOW_END = "2026-08-23 00:00:00"
EDITORIAL_ID = "palestine-weekly-2026-W34"

TITLE = "和平不能把巴勒斯坦人的生存權當成談判籌碼"
DEK = "當重建被綁在政治條件上、停火之下仍有空襲與土地掠奪，所謂和平就只是在管理巴勒斯坦人的苦難。"
BODY = """停火十個月後，真正該被追問的，不是哪一場會談又用了什麼新名稱，而是巴勒斯坦人是否終於能安全活著。本週的新聞給出的答案仍是否定的：加薩的外交進程停滯，空襲沒有停止；西岸的定居者暴力、軍事行動與定居點擴張，也沒有因「和平計畫」而暫停。

這不是否認談判的必要，而是拒絕讓談判成為遮蔽現實的布幕。英國《衛報》報導，納坦雅胡與美國特使庫許納的會談未取得突破，以色列總理仍主張哈瑪斯先解除武裝，才談撤軍與停火進展。[來源](https://www.theguardian.com/world/2026/aug/17/netanyahu-kushner-talks-gaza-israel-us-board-of-peace) 同一期間，半島電視台報導加薩市一間咖啡館遭空襲，至少六人死亡，包括一名兒童。[來源](https://www.aljazeera.com/news/2026/8/18/israeli-strike-reported-to-kill-at-least-six-in-gaza-city?traffic_source=rss) 這兩件事放在一起，揭露了停火政治最危險的矛盾：一方要求被圍困者先完成政治與軍事上的服從，另一方卻保留繼續動武的權力。

重建更不該成為懲罰平民的槓桿。庫許納公開表示，在哈瑪斯解除武裝前「不允許」加薩重建；與此同時，加薩家庭仍為乾淨用水與食物掙扎，援助即使進入，也可能因封鎖、道路與倉儲障礙而到不了需要的人手中。[來源](https://www.aljazeera.com/news/2026/8/19/why-aid-entering-gaza-may-not-reach-those-who-need-it?traffic_source=rss) 政治談判可以處理安全安排，但食物、醫療、飲水與住所不是獎品。把基本生存與一個武裝組織的決定綁在一起，實際承受代價的是沒有談判席位的兒童、病人與流離失所者。

西岸則提醒我們，巴勒斯坦問題從來不只等於加薩停火。BBC 報導，以色列為高度敏感的 E1 定居點計畫開放投標；英國外交大臣稱此舉不可接受且具破壞性。[來源](https://www.bbc.co.uk/news/articles/cly50gn1e54o?at_medium=RSS&at_campaign=rss) 人權觀察的報告則認為，受國家支持的定居者暴力正迫使巴勒斯坦社群遷離，並呼籲制裁與暫停軍事援助。[來源](https://www.aljazeera.com/news/2026/8/20/state-backed-israeli-settler-violence-forces-west-bank-displacement-hrw?traffic_source=rss) 這是 NGO 的法律與政策結論，不是法院的終局判決；但它與本週一連串圍困住宅、縱火、殺害平民及擴建定居點的報導互相印證，足以要求各國不能只停在口頭譴責。

究責同樣不能被「已展開調查」四個字取代。以色列軍方承認士兵曾向載有五歲女童 Hind Rajab 與家人的汽車開火，並宣布刑事調查。[來源](https://www.bbc.co.uk/news/articles/crl7yjlpx2po?at_medium=RSS&at_campaign=rss) 這是調查程序的開始，不是定罪，也不是正義已經完成。另一邊，英國、加拿大與澳洲譴責以色列拒絕就 2024 年世界中央廚房援助人員遇害案展開刑事調查。[來源](https://www.bbc.co.uk/news/articles/cvgl2pe09eno?at_medium=RSS&at_campaign=rss) 當受害者必須依靠施害一方的內部機制等待答案，國際社會的責任就不該只剩「關切」。

真正可信的和平，至少要同時做到三件事：停止對平民的攻擊並保障人道援助無阻進入；停止以重建和基本生活作為集體施壓工具；阻止西岸定居點擴張與定居者暴力，並建立可被外部檢驗的究責機制。這些不是對任何一方安全的否定，而是安全不能只屬於擁有軍隊、邊界控制與外交庇護的一方。

巴勒斯坦人不應先證明自己值得活著，才獲得食物、藥物、屋頂與土地。若和平方案不能先承認這一點，它管理的不是和平，而只是苦難的速度。"""


def main() -> None:
    store = MySqlEventStore(load_settings(".env"))
    store.initialize()
    cur = store._cursor()
    try:
        cur.execute("SHOW COLUMNS FROM t_palestine_news_items")
        columns = [row[0] for row in cur.fetchall()]
        cur.execute("SHOW COLUMNS FROM t_palestine_editorials")
        editorial_columns = [row[0] for row in cur.fetchall()]
        cur.execute(
            "SELECT id, news_id, title, source_id, source_name, url, summary, "
            "published_at, first_seen_at, raw_json FROM t_palestine_news_items "
            "WHERE language='en' AND first_seen_at >= %s AND first_seen_at < %s "
            "ORDER BY first_seen_at, id",
            (WINDOW_START, WINDOW_END),
        )
        rows = cur.fetchall()
        source_ids = [row[1] for row in rows]
        source_urls = [row[5] for row in rows]
        cited_urls = re.findall(r"\]\((https?://[^)]+)\)", BODY)
        raw = {
            "source_urls": source_urls,
            "cited_urls": cited_urls,
            "check_notes": [
                "Reviewed every matching English row, including raw metadata.",
                "Duplicate coverage and off-topic regional rows were retained in the audit source set but not used as factual support.",
                "Legal characterizations are attributed to their reporting body; an announced criminal investigation is not described as a conviction or final judgment.",
                "No paid external LLM API was called.",
            ],
        }
        cur.execute(
            "INSERT INTO t_palestine_editorials "
            "(editorial_id, title, dek, body_markdown, source_window_start, source_window_end, "
            "source_count, source_news_ids_json, model, prompt_version, generated_by, status, raw_json, published_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE title=VALUES(title), dek=VALUES(dek), body_markdown=VALUES(body_markdown), "
            "source_window_start=VALUES(source_window_start), source_window_end=VALUES(source_window_end), "
            "source_count=VALUES(source_count), source_news_ids_json=VALUES(source_news_ids_json), "
            "model=VALUES(model), prompt_version=VALUES(prompt_version), generated_by=VALUES(generated_by), "
            "status=VALUES(status), raw_json=VALUES(raw_json), published_at=VALUES(published_at)",
            (
                EDITORIAL_ID, TITLE, DEK, BODY, WINDOW_START, WINDOW_END, len(source_ids),
                json.dumps(source_ids, ensure_ascii=False), "codex", "palestine-weekly-editorial-v1",
                "codex-weekly-editorial", "published", json.dumps(raw, ensure_ascii=False),
                datetime.now(timezone.utc).replace(tzinfo=None),
            ),
        )
        store._conn.commit()
        cur.execute(
            "SELECT editorial_id, title, dek, body_markdown, source_window_start, source_window_end, "
            "source_count, source_news_ids_json, model, prompt_version, generated_by, status, raw_json, published_at "
            "FROM t_palestine_editorials WHERE editorial_id=%s",
            (EDITORIAL_ID,),
        )
        saved = cur.fetchone()
        saved_ids = json.loads(saved[7])
        saved_raw = json.loads(saved[12])
        saved_citations = re.findall(r"\]\((https?://[^)]+)\)", saved[3])
        validation = {
            "row_read_back": bool(saved),
            "traditional_chinese_readable": len(re.findall(r"[\u4e00-\u9fff]", saved[3])) >= 300,
            "no_mojibake_or_question_blocks": "�" not in saved[1] + saved[2] + saved[3] and not re.search(r"\?{3,}", saved[3]),
            "source_count_matches_ids": saved[6] == len(saved_ids) == len(set(saved_ids)),
            "no_raw_json_dump_in_body": "source_news_ids_json" not in saved[3] and "raw_json" not in saved[3],
            "citations_match_reviewed_urls": bool(saved_citations) and all(url in source_urls for url in saved_citations),
            "raw_check_notes_present": bool(saved_raw.get("check_notes")),
        }
        payload = {
            "window_start": WINDOW_START,
            "window_end": WINDOW_END,
            "columns": columns,
            "editorial_columns": editorial_columns,
            "rows": [dict(zip(["id", "news_id", "title", "source_id", "source_name", "url", "summary", "published_at", "first_seen_at", "raw_json"], row)) for row in rows],
            "saved": {
                "editorial_id": saved[0], "title": saved[1], "source_count": saved[6],
                "source_window_start": str(saved[4]), "source_window_end": str(saved[5]),
                "status": saved[11], "published_at": str(saved[13]),
            },
            "validation": validation,
        }
        json.dump(payload, sys.stdout, ensure_ascii=True, default=str)
    finally:
        cur.close()


if __name__ == "__main__":
    main()
