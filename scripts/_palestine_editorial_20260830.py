from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

from event_relay.config import load_settings
from event_relay.service import MySqlEventStore

WINDOW_START = "2026-08-23 00:00:00"
WINDOW_END = "2026-08-30 00:00:00"
EDITORIAL_ID = "palestine-weekly-2026-W35"
TITLE = "停火若保不住水、醫院與家園，就不能被稱為和平"
DEK = "加薩的空襲與生存危機、西岸的封鎖與土地侵奪同時延續；本週最重要的問題不是協議還在不在，而是平民是否真的受到保護。"
BODY = """一份停火協議可以留在文件上，戰爭卻仍能滲進每一個生活條件。本週的英語新聞反覆呈現同一幅圖像：加薩人一面被告知政治進程仍在運作，一面面對空襲、缺氧、糧食不安全與基礎設施受損；西岸居民則在定居者暴力、軍事攻擊、路障與土地侵奪下失去行動與生活空間。判斷和平是否存在，不能只看談判桌有沒有散會，而要看平民能不能活下來。

這不是抽象的修辭。8 月 25 日，半島電視台報導，以色列空襲擊中加薩一座水廠與援助物資倉庫，造成至少七人死亡；報導引述加薩衛生部門警告，基本生活條件面臨全面崩潰。[來源](https://www.aljazeera.com/news/2026/8/25/seven-killed-in-gaza-as-israeli-strike-destroys-aid-supply-warehouse?traffic_source=rss) 數日前，該台也報導加薩醫院氧氣短缺，使早產兒與重症患者承受直接風險。[來源](https://www.aljazeera.com/video/newsfeed/2026/8/23/gazas-hospitals-are-running-out-of-oxygen-as-healthcare-nears-collapse?traffic_source=rss) 8 月 28 日的另一輪空襲又造成五人死亡，其中三人來自同一家庭，而當地仍處於嚴重糧食不安全之中。[來源](https://www.aljazeera.com/news/2026/8/28/israeli-strikes-kill-five-people-including-three-from-one-family-in-gaza?traffic_source=rss)

援助抵達不等於生存已獲保障，停火存在也不等於暴力已停止。BBC 報導，負責加薩停火工作的和平委員會特使尼古拉・姆拉德諾夫批評以色列的攻擊，也批評哈瑪斯的行動，並警告去年十月停火若崩潰，區域可能走向「無法回頭」的局面。[來源](https://www.bbc.co.uk/news/articles/cew92l07kwzo?at_medium=RSS&at_campaign=rss) 這項警告是外交特使的政治判斷，不是法院認定；但它揭露一個應被正視的事實：把協議本身當成成果，會讓協議下持續發生的死亡變得不可見。

生存危機也不限於轟炸當下。《衛報》報導，加薩約 210 萬人口被壓縮在愈來愈小的土地上，超過八成溫室受毀，農民仍在缺水、缺肥料與人身風險下設法恢復糧食生產。[來源](https://www.theguardian.com/world/2026/aug/26/gaza-farmers-struggle-scraps-of-land-constant-threat) 這提醒我們，重建不能只被理解為未來某一天的大型工程。能否取水、耕種、就醫與安葬死者，就是當下的重建，也是平民尊嚴最基本的尺度。

同一週，BBC 報導以色列查封東耶路撒冷的聯合國近東巴勒斯坦難民救濟和工程處（UNRWA）訓練學院；在以色列通過限制該機構的法律後，這代表 UNRWA 在東耶路撒冷最後一處設施被關閉。[來源](https://www.bbc.co.uk/news/articles/c5yl89yrldpo?at_medium=RSS&at_campaign=rss) UNRWA 官員認為這是削弱難民機構與難民權利的行動；那是當事機構的判斷，不是國際法院的終局判決。然而，當提供教育、援助與難民服務的制度空間被持續壓縮，各國不能只把後果當成行政爭議。

西岸的新聞讓這種壓縮更加具體。BBC 追蹤一週的定居者攻擊，記錄巴勒斯坦居民遭受的暴力。[來源](https://www.bbc.co.uk/news/videos/c3wjq1188g9o?at_medium=RSS&at_campaign=rss) 半島電視台則報導，Qusra 在數週定居者圍困後，又出現三道新設的以色列閘門，居民憂心家園將被永久隔離。[來源](https://www.aljazeera.com/news/2026/8/28/new-israeli-roadblocks-entrench-siege-of-homes-in-west-banks-qusra?traffic_source=rss) 這些不是與加薩停火無關的零星事件；它們共同顯示，若土地、道路、學校與家園仍被逐步剝奪，所謂政治進程就可能只是在管理巴勒斯坦人的退讓。

真正可被相信的和平，至少要接受三項檢驗：平民攻擊是否停止，人道與醫療系統是否能不受阻礙地運作，以及西岸的定居點擴張與定居者暴力是否受到實際制止。對哈瑪斯或任何武裝行動的批判，不能成為放棄保護巴勒斯坦平民的理由；對以色列安全的承諾，也不能被解釋為以色列政府可以免於國際人道法與外部究責。

本週的新聞不是要我們在兩種口號之間選邊，而是要求一個更誠實的衡量方式：孩子能否在醫院獲得氧氣，家庭能否取得水與食物，農民能否走到自己的土地，難民服務能否繼續開門。若這些答案仍是否定的，停火就只是降低或改變暴力速度，而不是和平。"""


def main() -> None:
    store = MySqlEventStore(load_settings(".env"))
    store.initialize()
    cur = store._cursor()
    try:
        cur.execute("SELECT id, news_id, title, source_id, source_name, url, summary, published_at, first_seen_at, raw_json FROM t_palestine_news_items WHERE language='en' AND first_seen_at >= %s AND first_seen_at < %s ORDER BY first_seen_at, id", (WINDOW_START, WINDOW_END))
        rows = cur.fetchall()
        if not rows:
            print(json.dumps({"skipped": "no usable English Palestine news rows"}))
            return
        source_ids = [row[1] for row in rows]
        source_urls = [row[5] for row in rows]
        cited_urls = re.findall(r"\]\((https?://[^)]+)\)", BODY)
        raw = {"source_urls": source_urls, "cited_urls": cited_urls, "check_notes": ["Reviewed all matching rows and all requested fields, including raw metadata.", "All raw_json values parsed; duplicate coverage and off-topic feed leakage remain in the audit ID set but were not used as factual support.", "Diplomatic and UNRWA assessments are attributed and are not described as court judgments.", "No paid external LLM API was called."]}
        cur.execute("INSERT INTO t_palestine_editorials (editorial_id, title, dek, body_markdown, source_window_start, source_window_end, source_count, source_news_ids_json, model, prompt_version, generated_by, status, raw_json, published_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE title=VALUES(title), dek=VALUES(dek), body_markdown=VALUES(body_markdown), source_window_start=VALUES(source_window_start), source_window_end=VALUES(source_window_end), source_count=VALUES(source_count), source_news_ids_json=VALUES(source_news_ids_json), model=VALUES(model), prompt_version=VALUES(prompt_version), generated_by=VALUES(generated_by), status=VALUES(status), raw_json=VALUES(raw_json), published_at=VALUES(published_at)", (EDITORIAL_ID, TITLE, DEK, BODY, WINDOW_START, WINDOW_END, len(source_ids), json.dumps(source_ids, ensure_ascii=False), "codex", "palestine-weekly-editorial-v1", "codex-weekly-editorial", "published", json.dumps(raw, ensure_ascii=False), datetime.now(timezone.utc).replace(tzinfo=None)))
        store._conn.commit()
        cur.execute("SELECT editorial_id, title, dek, body_markdown, source_window_start, source_window_end, source_count, source_news_ids_json, model, prompt_version, generated_by, status, raw_json, published_at FROM t_palestine_editorials WHERE editorial_id=%s", (EDITORIAL_ID,))
        saved = cur.fetchone()
        saved_ids = json.loads(saved[7])
        saved_raw = json.loads(saved[12])
        saved_citations = re.findall(r"\]\((https?://[^)]+)\)", saved[3])
        validation = {"row_read_back": bool(saved), "traditional_chinese_readable": len(re.findall(r"[\u4e00-\u9fff]", saved[3])) >= 300, "no_mojibake_or_question_blocks": "�" not in saved[1] + saved[2] + saved[3] and not re.search(r"\?{3,}", saved[3]), "source_count_matches_ids": saved[6] == len(saved_ids) == len(set(saved_ids)), "no_raw_json_dump_in_body": "source_news_ids_json" not in saved[3] and "raw_json" not in saved[3], "citations_match_reviewed_urls": bool(saved_citations) and all(url in source_urls for url in saved_citations), "raw_check_notes_present": bool(saved_raw.get("check_notes"))}
        payload = {"saved": {"editorial_id": saved[0], "title": saved[1], "source_count": saved[6], "source_window_start": str(saved[4]), "source_window_end": str(saved[5]), "status": saved[11], "published_at": str(saved[13])}, "review": {"rows": len(rows), "unique_ids": len(set(source_ids)), "raw_json_parsed": sum(1 for row in rows if isinstance(json.loads(row[9] or "{}"), dict))}, "validation": validation}
        json.dump(payload, sys.stdout, ensure_ascii=True, default=str)
    finally:
        cur.close()


if __name__ == "__main__":
    main()
