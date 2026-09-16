"""Store the 2026-09-17 local-evidence U.S. close memo; dry-run by default."""
import json
import sys
from datetime import datetime, timedelta, timezone

from _us_close_guard_20260909 import (
    MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-09-17'
EVENT_IDS = [945481, 945283, 945634, 942336]
MARKET_IDS = [401, 402, 403, 404]
SUMMARY = """這次美股收盤對台灣投資人最直接的改變，是升息從預期變成現實，資金成本可能維持高檔的時間也更值得重估。美股主要指數在會後走弱，台灣電子產業即使仍有 AI 需求支撐，也要同時承受估值折現與能源成本的壓力。我的判斷偏審慎，但這還不是需求轉弱的證明；關鍵在於通膨壓力能否緩和，以及企業獲利能否跟上資金成本。

中央社報導，聯準會升息 0.25 個百分點，主席華許把物價穩定列為首要任務。市場原已預期升息，新增的不確定性在會後訊號：風傳媒記錄到股市與金價走低、美元及美債殖利率走高，市場開始重新評估後續緊縮的可能。這種組合會提高持有美元資產的吸引力，也會讓依賴遠期獲利的成長產業面對更嚴格的估值要求。不過，單晚的資產價格變動不能全歸因於一場記者會。

收盤資料給了較清楚的行情邊界：道瓊與標普都低於當日開盤，收盤報導也指出美股主要指數下跌。這說明升息後的風險偏好承壓，卻還不能由指數方向推斷每個產業都同步轉弱。另一條壓力來自能源：收盤報導把中東戰事與原油及通膨風險連在一起。油市盤中仍會波動，不能把衝突風險直接寫成當日結算油價；真正影響台灣企業的，是燃料、運輸與原料成本能否持續轉嫁。

台灣的傳導因產業而異。瑞銀論壇的報導認為，AI 需求仍強，電力與記憶體供應反而是擴張瓶頸。這是產業展望，不等於已實現的獲利；先進製程、伺服器、記憶體及電力設備鏈仍須用接單、產能與毛利率驗證。若美元與殖利率維持強勢，電子權值股可能先受估值壓縮，即使需求敘事沒有消失。航空、運輸與耗能製造則更直接面對能源成本，石化業還要看產品售價能否跟上原料漲幅。

眼前已反映的是升息決定與美股收盤賣壓，仍待重估的是緊縮會持續多久、油價衝擊是否擴散，以及 AI 投資能否轉成供應鏈利潤。若後續通膨降溫、殖利率回落，而半導體訂單與利潤保持韌性，審慎判斷就需要修正；若能源壓力延續、利率預期再上移，且企業開始下修獲利，成本與估值壓力可能互相強化。這是美股收盤視角，不能直接當成台股開盤後資金流向的結論。"""


def rows(cursor, sql, params=()):
    cursor.execute(sql, params)
    result = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
    return json.loads(json.dumps(result, default=str))


def main():
    calendar = resolve_market_calendar_state(datetime.now(timezone(timedelta(hours=8))))
    assert str(calendar.local_date) == DAY and 'us_close' in allowed_analysis_slots(calendar)
    writer = MySqlEventStore(load_settings('.env'))
    cursor = writer._cursor()
    assert not rows(cursor, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='us_close'", (DAY,)), 'Existing row needs separate review'
    events = rows(cursor, 'SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (945481,945283,945634,942336)')
    market = rows(cursor, 'SELECT id,trade_date,market_session,symbol,recorded_price FROM t_market_index_snapshots WHERE id IN (401,402,403,404)')
    assert {e['id'] for e in events} == set(EVENT_IDS)
    assert {m['id'] for m in market} == set(MARKET_IDS)
    assert all(str(m['trade_date']) == '2026-09-16' for m in market)
    for symbol in ('DJIA', 'S&P 500'):
        prices = {m['market_session']: float(m['recorded_price']) for m in market if m['symbol'] == symbol}
        assert prices['close'] < prices['open']
    structured = dict(schema_version='codex-market-analysis-v1', confidence='medium',
        thesis='升息落地後，資金成本與能源風險牽動台灣電子估值；AI 需求仍須以獲利驗證。',
        evidence_event_ids=EVENT_IDS, market_snapshot_ids=MARKET_IDS,
        tw_sector_transmission=['電子估值與接單獲利分開檢驗', '能源成本影響運輸與製造', '記憶體及電力供給制約 AI 擴張'],
        invalidation=['通膨與殖利率回落，且半導體訂單及利潤維持韌性'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=market)
    style = style_check(SUMMARY)
    assert verifier['ok'] and style['ok'], json.dumps(dict(verifier=verifier, style=style), ensure_ascii=False)
    push = not calendar.tw.is_trading_day
    raw = dict(automation_id='market-analysis-codex-guard-us-close', generator='codex_automation',
        display_title=DAY, calendar=calendar.to_dict(), evidence_event_ids=EVENT_IDS,
        market_snapshot_ids=MARKET_IDS, claim_verifier=verifier,
        trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'),
        style_checks=style, external_provider_api_called=False)
    print(json.dumps(dict(dry_run=True, claim_verifier=verifier, style_checks=style, push_enabled=push), ensure_ascii=False))
    if '--write' not in sys.argv:
        return
    row_id = writer.upsert_market_analysis(MarketAnalysisRecord(analysis_date=DAY, analysis_slot='us_close',
        scheduled_time_local='05:00', model='codex-local-judgment', prompt_version='codex-flexible-briefing-memo-v1',
        summary_text=SUMMARY, events_used=len(events), market_rows_used=len(market), push_enabled=push, pushed=False,
        raw_json=json.dumps(raw, ensure_ascii=False), structured_json=json.dumps(structured, ensure_ascii=False)))
    reader = MySqlEventStore(load_settings('.env'))
    read_cursor = reader._cursor()
    row = rows(read_cursor, 'SELECT summary_text,raw_json,structured_json,push_enabled,pushed FROM t_market_analyses WHERE id=%s', (row_id,))[0]
    signals = rows(read_cursor, 'SELECT COUNT(*) n FROM t_trade_signals WHERE analysis_id=%s', (row_id,))[0]['n']
    stored_raw = json.loads(row['raw_json'])
    stored_structured = json.loads(row['structured_json'])
    assert row['summary_text'] == SUMMARY and stored_raw == raw and stored_structured == structured
    assert bool(row['push_enabled']) == push and not row['pushed'] and signals == 0
    assert style_check(row['summary_text'])['ok'] and not stored_raw['external_provider_api_called']
    print(json.dumps(dict(analysis_id=row_id, claim_verifier_ok=stored_raw['claim_verifier']['ok'],
        trust_gate=stored_raw['trust_gate'], push_enabled=push, pushed=False,
        structured_json_present=bool(stored_structured), garbled_text=style_check(row['summary_text'])['garbled_text'],
        style_checks=style_check(row['summary_text']), external_provider_api_called=False,
        trade_signal_count=signals), ensure_ascii=False))


if __name__ == '__main__':
    main()
