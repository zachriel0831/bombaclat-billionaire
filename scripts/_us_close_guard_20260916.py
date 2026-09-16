"""Local-only close memo; dry-run unless --write is supplied."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260909 import (
    MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-09-16'
IDS = [937056, 936652, 937627, 937632]
SUMMARY = """這次美股收盤帶給台灣投資人的變化，是半導體出現止跌跡象，但整體資金環境仍未鬆綁。我的判斷偏審慎：台灣電子供應鏈的壓力開始出現分化，還不足以說成全面回穩。能源供應受阻與公債殖利率偏高，仍可能壓縮企業利潤及市場願意給出的估值；最大的變數，是這些成本壓力會延續多久，以及聯準會如何回應。

中央社的美股收盤報導指出，主要指數收跌，費城半導體指數卻微幅收高。收盤行情中的費半漲幅為 0.40%，但台積電美國存託憑證仍下跌。這個落差對台灣特別重要：產業指數轉強，只能說明部分晶片股暫時獲得支撐，不能直接推論台灣權值電子同步解除壓力，更不能據此確認訂單轉好。先進製程、封裝與伺服器供應鏈接下來仍要靠企業投資進度、營收及利潤來驗證，單晚反彈提供的是喘息空間。

油市的壓力有具體供應背景。原油收盤報導提到，沙烏地受損輸油管線關閉，利比亞也傳出管線閥門遭關閉、部分油田停產，國際油價因而走高。這類供應衝擊可能同時拉高成本、削弱其他消費，不宜當成需求強勁的訊號。對台灣航空、運輸與耗能製造而言，影響先落在燃料與生產成本；石化則取決於產品售價能否跟上原料漲幅，不能把油價上漲一概理解為產業獲利改善。

同一份美股收盤報導也指出，美國公債殖利率走高，投資人等待聯準會利率決策。能源與利率因此形成雙重約束：油價若使通膨更難下降，貨幣政策能提供的緩衝就可能受限；較高的資金成本又會降低遠期獲利的現值。台灣 AI 供應鏈即使維持成長，也可能面對更嚴格的估值要求。金融業則須分辨債券部位評價、資金成本與利差的不同效果，不能只用利率上升就判定整體利多或利空。

盤面已呈現大盤偏弱、半導體相對有支撐的分化，但沒有足夠證據判定能源衝擊已反映充分。仍可能改變定價的，是供應恢復速度、政策訊息，以及企業能否把成本轉嫁出去。若油市供應緩和、殖利率回落，且半導體強勢擴散到台灣主要供應鏈，這份審慎判斷就需要調整；若供應中斷延續、利率壓力升高，或企業開始下修獲利，則短暫止跌不足以扭轉成本與估值壓力。本篇以美股收盤為觀察時點，不據此判定台灣當日盤中資金流向。"""


def main():
    calendar = resolve_market_calendar_state(datetime.now(timezone(timedelta(hours=8))))
    assert str(calendar.local_date) == DAY and 'us_close' in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings('.env'))
    c = store._cursor()
    def rows(sql, params=()):
        c.execute(sql, params)
        return json.loads(json.dumps([dict(zip([d[0] for d in c.description], r)) for r in c.fetchall()], default=str))
    assert not rows("SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='us_close'", (DAY,))
    events = rows('SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (%s,%s,%s,%s)', IDS)
    assert len(events) == 4
    for event in events:
        published = datetime.fromisoformat(event['published_at']).astimezone(timezone(timedelta(hours=8)))
        assert published.date().isoformat() == DAY and published.hour < 7
    structured = dict(schema_version='codex-market-analysis-v1', confidence='medium',
        thesis='半導體止跌與大盤弱勢分化，台灣仍面對能源成本及利率約束。',
        evidence_event_ids=IDS,
        tw_sector_transmission=['先進製程、封裝與伺服器仍須驗證獲利', '航空、運輸與耗能製造承受成本壓力', '金融業須分辨評價與利差效果'],
        invalidation=['能源供應緩和、殖利率回落且半導體強勢擴散'],
        caveat='收盤視角；產業指數反彈不能證明訂單改善。')
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = style_check(SUMMARY)
    assert verifier['ok'] and style['ok'], json.dumps(dict(verifier=verifier, style=style))
    raw = dict(automation_id='market-analysis-codex-guard-us-close', generator='codex_automation', display_title=DAY,
        calendar=calendar.to_dict(), evidence_event_ids=IDS, claim_verifier=verifier,
        trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'),
        style_checks=style, external_provider_api_called=False)
    push = not calendar.tw.is_trading_day
    print(json.dumps(dict(dry_run=True, verifier=verifier, style=style, push_enabled=push)))
    if '--write' not in sys.argv:
        return
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(analysis_date=DAY, analysis_slot='us_close',
        scheduled_time_local='05:00', model='codex-local-judgment', prompt_version='codex-flexible-briefing-memo-v1',
        summary_text=SUMMARY, events_used=len(events), market_rows_used=0, push_enabled=push, pushed=False,
        raw_json=json.dumps(raw, ensure_ascii=False), structured_json=json.dumps(structured, ensure_ascii=False)))
    # A fresh connection checks committed state independently of the writer.
    reader = MySqlEventStore(load_settings('.env'))
    c = reader._cursor()
    row = rows('SELECT summary_text,raw_json,structured_json,push_enabled,pushed FROM t_market_analyses WHERE id=%s', (row_id,))[0]
    count = rows('SELECT COUNT(*) n FROM t_trade_signals WHERE analysis_id=%s', (row_id,))[0]['n']
    assert row['summary_text'] == SUMMARY and json.loads(row['raw_json']) == raw
    assert json.loads(row['structured_json']) == structured and bool(row['push_enabled']) == push
    assert not row['pushed'] and count == 0 and style_check(row['summary_text'])['ok']
    print(json.dumps(dict(analysis_id=row_id, claim_verifier_ok=verifier['ok'], trust_gate=raw['trust_gate'],
        push_enabled=push, pushed=False, structured_json_present=True, style_checks=style,
        external_provider_api_called=False, trade_signal_count=count)))


if __name__ == '__main__':
    main()
