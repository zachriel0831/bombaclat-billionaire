from __future__ import annotations

import json
import re

from event_relay.config import load_settings
from event_relay.service import MarketAnalysisRecord, MySqlEventStore


ANALYSIS_DATE = "2026-08-23"
SLOT = "weekly_tw_preopen"
SECTION_CONTRACT = ["週總經", "下週台股配置", "下週觀察清單"]
CONTEXT_IDS = [
    726120, 726121, 734910, 734911, 734912, 734913, 734914,
    734937, 734938, 734946, 734950, 734951, 734952,
]
NEWS_IDS = [724332, 730359, 731147, 736877]

SUMMARY = """## 週總經

本週主命題是：市場不是在交易景氣立即失速，而是在重新計算「高利率與高能源成本，會把成長股評價壓到哪裡」。那斯達克100從約三萬零四十六點降至二萬九千三百零九點，約回落百分之二點五；費城半導體指數由約一萬二千四百一十七點降至一萬一千七百四十點，跌幅約百分之五點五。科技鏈明顯降溫，但VIX仍在十五附近，等權重相對大型權值的參與度則由負轉正，顯示資金偏向輪動，而非全面撤離風險資產。

利率是第一道估值上限。美國二年期與十年期公債殖利率最新約為百分之四點一九與四點六九，十年減二年利差約零點五個百分點；高收益債利差從百分之二點六七升至二點七五，壓力增加但尚未呈現信用市場失序。市場已反映短期不易快速寬鬆，尚未完全反映的風險，是長債供給與財政疑慮若再推升期限溢酬，科技股即使獲利成長仍可能面臨本益比收縮。

第二道壓力來自能源與政策。WTI原油由約八十二點四美元升至八十六點六美元，週升約百分之五；美元指數則由約九十九點六降至九十八點八。美元轉弱替風險資產提供部分緩衝，但美伊經濟對抗、能源設施與運輸風險，以及美加關稅衝突，都可能把成本壓力重新送回通膨與利率。基準情境仍是景氣韌性下的類股輪動，反證條件是信用利差明顯擴大、VIX快速升高且市場廣度同步惡化；若油價回落、長債殖利率下行且半導體重新領漲，則本週偏保守判斷應調高。

## 下週台股配置

台股宜維持中性偏防守的槓鈴配置：一端保留AI伺服器、先進封裝、記憶體與高階半導體等有資本支出支撐的主線，另一端提高金融、電信、公用事業與現金流穩定族群的比重。半導體不是需求敘事消失，而是海外科技股回檔與高殖利率會先壓縮評價；台積電等大型權值股可作為全球AI風險偏好的傳導指標，不宜把單一題材當成全電子族群同步上漲的保證。

油價上行對台灣是分化訊號。上游原料與部分報價受惠產業可能得到支撐，但航空、運輸、塑化下游與高耗能製造的成本壓力會增加。美元偏弱若延續，有利外資風險承擔，卻也可能壓縮出口商匯兌利益；因此下週配置重點是獲利能見度與議價能力，而不是追逐地緣政治消息。若美債殖利率再升且費城半導體續弱，應降低高評價成長曝險；若殖利率回落、信用利差穩定且半導體廣度改善，可再把權重移回科技主線。

## 下週觀察清單

- 先看美國十年期公債殖利率與高收益債利差：前者決定科技股評價上限，後者用來辨認輪動是否惡化成信用風險。
- 再看WTI油價與美伊制裁、能源運輸消息：若油價續升，通膨預期與台灣耗能產業成本可能同步上修。
- 觀察那斯達克100、費城半導體與等權重指標能否同時轉強；只有權值反彈而廣度未跟上，行情仍偏脆弱。
- 留意美加關稅摩擦與其他貿易政策是否擴散，評估電子零組件、汽車供應鏈與出口訂單的第二輪影響。
- 資料缺口是本週缺少完整的台股週線成交結構與一致口徑的法人流向彙總，因此配置結論主要依跨資產價格、國際政策與產業傳導判斷，信心維持中等。
"""


def text_checks(text: str) -> dict[str, object]:
    headings = re.findall(r"^##\s+(.+?)\s*$", text, flags=re.MULTILINE)
    garbled = bool(re.search(r"\?{3,}|\ufffd|[\ue000-\uf8ff]|銝|蝢||", text))
    forbidden = [
        term for term in [
            "入場", "停損", "止損", "目標價", "target price", "stop-loss",
            "t_relay_events", "t_market_analyses", "market_context", "raw_json",
            "Codex guard", "LLM API", "stock_watch",
        ] if term.lower() in text.lower()
    ]
    return {
        "ok": headings == SECTION_CONTRACT and not garbled and not forbidden,
        "headings": headings,
        "garbled_text": garbled,
        "forbidden_terms": forbidden,
    }


def main() -> None:
    checks = text_checks(SUMMARY)
    if not checks["ok"]:
        raise RuntimeError(json.dumps(checks, ensure_ascii=False))

    store = MySqlEventStore(load_settings(".env"))
    store.initialize()
    cursor = store._cursor()
    try:
        ids = CONTEXT_IDS + NEWS_IDS
        placeholders = ",".join(["%s"] * len(ids))
        cursor.execute(
            f"SELECT id, source, title, published_at, created_at FROM t_relay_events "
            f"WHERE id IN ({placeholders}) ORDER BY id",
            tuple(ids),
        )
        evidence = [
            {"id": int(row[0]), "source": str(row[1]), "title": str(row[2]),
             "published_at": str(row[3] or ""), "created_at": str(row[4] or "")}
            for row in cursor.fetchall()
        ]
        cursor.execute("SELECT COUNT(*) FROM t_event_embeddings")
        event_embeddings = int(cursor.fetchone()[0])
        cursor.execute("SELECT COUNT(*) FROM t_analysis_embeddings")
        analysis_embeddings = int(cursor.fetchone()[0])
    finally:
        cursor.close()
    if {row["id"] for row in evidence} != set(ids):
        raise RuntimeError("required local evidence rows are missing")

    raw = {
        "automation_id": "market-analysis-codex-guard-weekly",
        "generator": "codex_automation",
        "dimension": "weekly",
        "delivery_owner": "java",
        "section_contract": SECTION_CONTRACT,
        "evidence_event_ids": ids,
        "market_context_event_ids": CONTEXT_IDS,
        "news_event_ids": NEWS_IDS,
        "rag": {
            "event_embeddings_available": event_embeddings,
            "analysis_embeddings_available": analysis_embeddings,
            "usage": "availability_only",
        },
        "style_checks": checks,
        "external_provider_api_called": False,
    }
    structured = {
        "schema_version": "codex-weekly-three-section-v1",
        "thesis": "高利率與油價壓抑成長股評價，但市場廣度改善顯示資金偏向輪動而非全面撤退。",
        "confidence": "medium",
        "evidence_event_ids": ids,
        "invalidation": [
            "信用利差明顯擴大、VIX快速升高且市場廣度同步惡化",
            "油價回落、長債殖利率下行且半導體重新廣泛領漲",
        ],
    }
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(
        analysis_date=ANALYSIS_DATE,
        analysis_slot=SLOT,
        scheduled_time_local="05:10",
        model="codex-local-judgment",
        prompt_version="codex-weekly-three-section-v1",
        summary_text=SUMMARY,
        events_used=len(evidence),
        market_rows_used=len(CONTEXT_IDS),
        push_enabled=True,
        pushed=False,
        raw_json=json.dumps(raw, ensure_ascii=False),
        structured_json=json.dumps(structured, ensure_ascii=False),
    ))

    cursor = store._cursor()
    try:
        cursor.execute(
            "SELECT id, analysis_date, scheduled_time_local, prompt_version, summary_text, "
            "events_used, market_rows_used, push_enabled, pushed, raw_json "
            "FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot=%s",
            (ANALYSIS_DATE, SLOT),
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
    if not row:
        raise RuntimeError("weekly analysis row missing after upsert")
    stored_raw = json.loads(row[9])
    stored_checks = text_checks(str(row[4]))
    result = {
        "analysis_id": int(row[0]),
        "analysis_date": str(row[1]),
        "scheduled_time_local": str(row[2]),
        "prompt_version": str(row[3]),
        "section_order": stored_checks["headings"],
        "garbled_text": stored_checks["garbled_text"],
        "forbidden_terms": stored_checks["forbidden_terms"],
        "events_used": int(row[5]),
        "market_rows_used": int(row[6]),
        "push_enabled": bool(row[7]),
        "pushed": bool(row[8]),
        "dimension": stored_raw.get("dimension"),
        "delivery_owner": stored_raw.get("delivery_owner"),
        "raw_section_contract": stored_raw.get("section_contract"),
        "external_provider_api_called": stored_raw.get("external_provider_api_called"),
    }
    expected = {
        "analysis_date": ANALYSIS_DATE,
        "scheduled_time_local": "05:10",
        "prompt_version": "codex-weekly-three-section-v1",
        "section_order": SECTION_CONTRACT,
        "garbled_text": False,
        "forbidden_terms": [],
        "push_enabled": True,
        "pushed": False,
        "dimension": "weekly",
        "delivery_owner": "java",
        "raw_section_contract": SECTION_CONTRACT,
        "external_provider_api_called": False,
    }
    if any(result[key] != value for key, value in expected.items()):
        raise RuntimeError(json.dumps(result, ensure_ascii=False))
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
