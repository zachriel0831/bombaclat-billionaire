"""Local evidence memo; dry-run first, --write only for the missing daily row."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260917 import (
    rows, MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-09-24'
EVENT_IDS = [999638, 999478, 999217]
SUMMARY = """這次美股收盤讓台灣投資人需要重新衡量的，是企業需求仍有韌性，卻未必能換來更寬鬆的資金環境。油價與美債殖利率同步走高、美股收低，意味台灣電子產業可能同時面對估值折現與營運成本的壓力。判斷偏審慎，但不能把單晚股市下跌直接等同訂單衰退；最大的變數，是經濟強勢與能源風險是否讓高利率維持更久。

中央社報導，美國商業調查表現強勁，市場對經濟過熱與聯準會再升息的疑慮升高，美債殖利率隨之上揚。這裡需要分開的是，調查偏強可以支撐需求展望，卻也可能壓低市場對寬鬆的期待。對依賴未來獲利成長的電子與半導體而言，營收前景改善和估值上修並不是同一件事：當折現率提高，即使訂單沒有轉差，市場願意支付的評價仍可能下降。再升息目前是市場擔憂，不能寫成已確定的政策。

經濟日報的收盤報導則指出，油價、美債殖利率齊揚，美股收低，並提到伊朗總統強硬表態。道瓊與標普的當日行情也都收在開盤之下，與收盤報導的偏弱方向一致，但開收盤差並非相對前一交易日的漲跌幅。能源與利率同時帶來壓力，是這個窗口較值得重視的組合；至於各項消息分別造成多少跌幅，單晚行情無法精確拆解。外交接觸若沒有轉成供應及航運改善，企業面對的能源成本就未必能很快下降。

另據經濟日報引述經濟合作暨發展組織的警告，公債殖利率上升、利息支出負擔加重，正在增加公共財政風險。這提供的是中期約束：政府若要維持支出，融資成本可能侵蝕其他預算空間，也讓債券市場更在意財政路徑。它不能直接證明當晚殖利率完全由財政因素推升，更不代表金融危機已經發生；但足以提醒，未來資金成本不能只用一次景氣數據推算。

傳到台灣，先進製程、AI 伺服器與設備鏈要把需求、毛利率和估值拆開驗證。若客戶投資與接單仍強，獲利可能抵銷部分利率壓力；若資金成本上升又伴隨支出遞延，傳導才會從評價延伸到營運。航空、陸運及耗能製造則更直接承受燃料成本，石化業還須看產品售價相對原料的價差。美元若進一步走強，進口成本與外資換匯條件也可能改變，但這是後續條件，不能當成當晚已確認的匯率結果。

目前價格已呈現油價、殖利率走高與股票承壓，尚不能斷言市場已充分反映衝擊。接下來可能再定價的，是高利率延續時間、能源供應改善速度，以及企業能否保住利潤。若油價回落、通膨壓力減輕，殖利率趨穩且電子訂單維持韌性，這份審慎判斷就應轉向較正面；若能源壓力延續、利率預期再上移，並出現獲利下修，成本與估值壓力可能相互強化。台股是否承接這條傳導，仍須由開盤後的產業表現與資金流向確認。"""


def main():
    calendar = resolve_market_calendar_state(datetime.now(timezone(timedelta(hours=8))))
    assert str(calendar.local_date) == DAY and 'us_close' in allowed_analysis_slots(calendar)
    writer = MySqlEventStore(load_settings('.env'))
    cur = writer._cursor()
    assert not rows(cur, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='us_close'", (DAY,))
    events = rows(cur, 'SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (999638,999478,999217)')
    market = rows(cur, 'SELECT id,trade_date,market_session,symbol,recorded_price FROM t_market_index_snapshots WHERE id IN (421,422,423,424)')
    assert {e['id'] for e in events} == set(EVENT_IDS)
    assert all(e['published_at'][:10] == DAY for e in events)
    assert len(market) == 4 and all(m['trade_date'] == str(calendar.us_close_session_date) for m in market)
    for symbol in ('DJIA', 'S&P 500'):
        prices = {m['market_session']: float(m['recorded_price']) for m in market if m['symbol'] == symbol}
        assert prices['close'] < prices['open']
    structured = dict(schema_version='codex-market-analysis-v1', confidence='medium',
        thesis='能源與利率同升使台灣電子估值及營運成本承壓，需求韌性仍須獲利驗證。',
        evidence_event_ids=EVENT_IDS, market_snapshot_ids=[421,422,423,424],
        tw_sector_transmission=['電子估值與獲利', '運輸與耗能製造成本', '石化產品原料價差'],
        invalidation=['油價回落、殖利率趨穩且電子需求維持韌性', '能源及利率壓力延續並伴隨獲利下修'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=market)
    style = style_check(SUMMARY)
    assert verifier['ok'] and style['ok'], (verifier, style)
    push = not calendar.tw.is_trading_day
    raw = dict(automation_id='market-analysis-codex-guard-us-close', generator='codex_automation',
        display_title=DAY, calendar=calendar.to_dict(), evidence_event_ids=EVENT_IDS,
        market_snapshot_ids=[421,422,423,424], claim_verifier=verifier,
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
    rc = reader._cursor()
    row = rows(rc, 'SELECT summary_text,raw_json,structured_json,push_enabled,pushed FROM t_market_analyses WHERE id=%s', (row_id,))[0]
    signals = rows(rc, 'SELECT COUNT(*) n FROM t_trade_signals WHERE analysis_id=%s', (row_id,))[0]['n']
    assert row['summary_text'] == SUMMARY and json.loads(row['raw_json']) == raw and json.loads(row['structured_json']) == structured
    assert bool(row['push_enabled']) == push and not row['pushed'] and signals == 0
    print(json.dumps(dict(analysis_id=row_id, claim_verifier_ok=verifier['ok'], trust_gate=raw['trust_gate'],
        push_enabled=push, pushed=False, structured_json_present=True, style_checks=style_check(row['summary_text']),
        external_provider_api_called=json.loads(row['raw_json'])['external_provider_api_called'], trade_signal_count=signals,
        characters=len(SUMMARY)), ensure_ascii=False))


if __name__ == '__main__':
    main()
