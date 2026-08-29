from __future__ import annotations

import json
import re

from event_relay.config import load_settings
from event_relay.service import MarketAnalysisRecord, MySqlEventStore


ANALYSIS_DATE = "2026-08-30"
SLOT = "weekly_tw_preopen"
SECTION_CONTRACT = ["週總經", "下週台股配置", "下週觀察清單"]
CONTEXT_IDS = [
    749793, 749794, 742950, 742951,
    790850, 790851, 790853, 790854,
    790870, 790871, 790886, 790889,
    790890, 790891, 790892,
    790900, 790901, 790902,
]
NEWS_IDS = [778888, 786841, 788494, 790476]

SUMMARY = """## 週總經

本週主命題是：市場正在交易「AI獲利繼續擴張，但資金成本不會很快下來」。台股加權指數從約四萬四千七百六十二點升至四萬六千三百三十一點，週幅約百分之三點五；金融保險與半導體類指數分別約升百分之三點八與二點八。輝達財報優於市場預期，台灣資通產品與對美出口比重上升，讓 AI 需求到台灣供應鏈的傳導仍有基本面支撐。

但美股的證據並不一致。那斯達克一百指數週內約升百分之零點四，費城半導體指數卻約跌百分之二點三，表示市場已先反映 AI 獲利成長，卻沒有願意無限擴張晶片股評價。美國兩年與十年期公債殖利率最新約為百分之四點三四與四點七三，Fed 主席重申通膨約束後，市場必須重新估算升息或高利率延長的可能性。已反映的是 AI 需求韌性；還沒有完全反映的，是若通膨黏著、長債供給壓力不退，高評價資產可能同時遭遇利率與集中度折價。

目前還不是系統性撤退：高收益債利差約百分之二點六三，VIX 約十四點五，信用與恐慌指標都仍受控。原油週內從約八十七美元回落至八十三點四美元，通膨壓力略得緩衝，但美元指數回到約九十九點七，反映高利率仍支撐美元。基準情境是獲利主導的類股輪動，不是全面風險趨避。

## 下週台股配置

下週建議維持中性偏多的槓鈴結構。一端保留 AI 伺服器、先進製程、先進封裝、電源散熱與高速傳輸等獲利能見度較高的主線；另一端配置金融、電信、公用事業與現金流穩定族群，降低利率上行對整體評價的衝擊。台積電可當作全球 AI 風險偏好的傳導節點，但輝達財報利多與費半週跌同時存在，意味選擇獲利可見度比擴大整體電子曝險更重要。

油價回落對航空、運輸、塑化下游與高耗能製造是成本利多，但中東運輸與制裁議題仍在，不宜把一週油價下跌外推成供給風險已解除。若美元與美債殖利率繼續上行，應降低只靠遠期故事支撐的高評價比重；若利率回落、費半止跌且等權重市場廣度改善，才能把這個配置調高為更明確的進攻。

## 下週觀察清單

- 先看美國兩年、十年期公債殖利率與後續 Fed 訊息：若兩者再上行，高利率延長將取代降息想像，成為成長股新的評價上限。
- 追蹤費城半導體、那斯達克一百與等權重指標：若財報利多後費半仍無法轉強，代表 AI 交易正從獲利成長轉向評價與擁擠度審查。
- 觀察美元與外資流向：美元續強會放大台股高檔波動；若外資與內資同步回補，才有利從大型權值擴散至中型供應鏈。
- 看 WTI 原油與中東運輸風險：油價回落若能持續，可緩和通膨與台灣進口成本；若再度急升，則利率與製造成本會同時受壓。
- 破局條件是高收益債利差顯著擴大、VIX 快速上升，且台股與美股市場廣度同步惡化；若沒有這組證據，回檔仍應優先解讀為評價輪動。本週缺少統一口徑的整週台股法人流向彙總，對資金廣度的信心維持中等。
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
        "thesis": "AI獲利與台灣出口支撐偏多結構，但偏鷹Fed與費半落後要求配置保留防守端。",
        "confidence": "medium",
        "evidence_event_ids": ids,
        "invalidation": [
            "高收益債利差顯著擴大、VIX快速上升且市場廣度同步惡化",
            "利率回落、費半止跌且等權重市場廣度改善",
        ],
    }
    store.upsert_market_analysis(MarketAnalysisRecord(
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
