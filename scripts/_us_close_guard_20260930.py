"""Store a limited-evidence memo using local facts only; dry-run by default."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260917 import (
    rows, MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-09-30'
TOKENS = {1033951: 'change_percent=-1.61%', 1033956: 'change_percent=+0.50%',
          1033971: 'value=5.24;'}
SUMMARY = '''這個美股收盤時點，尚無足夠的最新行情證據，能確認台灣投資人面對的風險偏好已經改變。較早一個美國交易日呈現的半導體分化與資金成本壓力，仍是評估台灣電子業的背景；它們不能直接當作昨夜收盤結果。眼前較合理的判斷是維持審慎，並把企業需求與股票估值分開檢驗，等待新的價格與獲利證據。

最近可核對的半導體行情屬於美國週一時段：費城半導體指數下跌 1.61%，台積電美國存託憑證則上漲 0.50%。這個差異反映大型晶圓製造企業與產業整體表現並不同步，卻沒有證明半導體訂單全面改善。若少數權值較有韌性，而其他企業表現偏弱，指數或單一企業的支撐就不足以代表風險偏好普遍回升。尤其美國存託憑證的漲跌不能直接套用到台灣現股，更不能由週一價格推論週二的方向。

另一項已知背景是美國週一的十年期公債殖利率為 5.24%。這是既有日頻水準，既不是最新一晚的升降，也不是央行政策利率。它的重要性在於資金成本如何約束估值：即使企業營收有成長，較遠期的現金流仍可能被給予較低的現值。要提高對電子產業的信心，需要接單、交付與利潤支持，不能只靠市場期待利率下降。

傳導到台灣，先進製程、封裝、設備與伺服器供應鏈須分別檢驗需求是否落實，以及成長能否轉為現金流。台積電可作為大型晶圓製造的傳導例子，但其海外股價韌性不能取代其他供應鏈的獲利證據。金融業受到的影響也有兩面：公債殖利率水準會影響新增資金的收益條件，利率後續若上升，既有債券又可能面對評價壓力；還要看持有期限與避險成本，不能概括為整個產業受惠。

目前只能說較早行情已呈現半導體內部分化，無法確認最新價格吸收了多少利率或需求預期。接下來的再定價，取決於資金成本是否緩和，以及企業獲利能否提供更廣泛的支撐。若新的半導體收盤表現改善並擴散，殖利率回落且企業展望維持韌性，審慎判斷就應調整；若權值支撐消退、弱勢擴大，又伴隨融資成本增加或獲利下修，壓力便可能由估值延伸到基本面。最新美股收盤與台灣資金反應仍待確認，因此這份摘要是條件分析，不能解讀成隔夜市場已選定方向。'''


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    cal = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and 'us_close' in allowed_analysis_slots(cal)
    writer = MySqlEventStore(load_settings('.env'))
    cur = writer._cursor()
    assert not rows(cur, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='us_close'", (DAY,))
    events = rows(cur, 'SELECT id,source,title,summary,published_at FROM t_relay_events WHERE id IN (1033951,1033956,1033971)')
    assert {e['id'] for e in events} == set(TOKENS)
    for event in events:
        assert TOKENS[event['id']] in event['summary'] and event['published_at'].startswith('2026-09-28')
    assert not rows(cur, "SELECT id FROM t_market_index_snapshots WHERE trade_date='2026-09-29' AND market_session='close'"), 'New close evidence requires editorial review'
    assert not rows(cur, 'SELECT id FROM t_relay_events WHERE id>1034025 LIMIT 1'), 'New evidence requires editorial review'
    structured = dict(schema_version='codex-market-analysis-v1', confidence='low',
        thesis='最新美股收盤未確認；較早半導體分化與利率水準僅支持條件式台灣傳導分析。',
        evidence_event_ids=list(TOKENS), market_snapshot_ids=[],
        tw_sector_transmission=['電子供應鏈需求與估值分開檢驗', '金融債券收益與評價風險'],
        invalidation=['半導體廣度改善、殖利率回落且企業展望穩健', '權值支撐消退且融資成本增加或獲利下修'],
        limitations=['Latest US session 2026-09-29 close unavailable; evidence as of 2026-09-28'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = style_check(SUMMARY)
    assert verifier['ok'] and style['ok'], (verifier, style)
    push = not cal.tw.is_trading_day
    raw = dict(automation_id='market-analysis-codex-guard-us-close', generator='codex_automation',
        display_title=DAY, calendar=cal.to_dict(), evidence_event_ids=list(TOKENS),
        claim_verifier=verifier, trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'),
        style_checks=style, external_provider_api_called=False, generated_at=now.isoformat(),
        evidence_freshness=dict(status='limited', current_us_close_available=False, evidence_date='2026-09-28'))
    print(json.dumps(dict(dry_run='--write' not in sys.argv, verifier=verifier, style=style, push_enabled=push), ensure_ascii=False))
    if '--write' not in sys.argv:
        return
    row_id = writer.upsert_market_analysis(MarketAnalysisRecord(analysis_date=DAY, analysis_slot='us_close',
        scheduled_time_local='05:00', model='codex-local-judgment', prompt_version='codex-flexible-briefing-memo-v1',
        summary_text=SUMMARY, events_used=len(events), market_rows_used=0, push_enabled=push, pushed=False,
        raw_json=json.dumps(raw, ensure_ascii=False), structured_json=json.dumps(structured, ensure_ascii=False)))
    reader = MySqlEventStore(load_settings('.env'))
    rc = reader._cursor()
    row = rows(rc, 'SELECT summary_text,raw_json,structured_json,push_enabled,pushed FROM t_market_analyses WHERE id=%s', (row_id,))[0]
    signals = rows(rc, 'SELECT COUNT(*) n FROM t_trade_signals WHERE analysis_id=%s', (row_id,))[0]['n']
    assert row['summary_text'] == SUMMARY and json.loads(row['raw_json']) == raw and json.loads(row['structured_json']) == structured
    assert bool(row['push_enabled']) == push and not row['pushed'] and signals == 0
    assert 'stock_watch' not in row['structured_json']
    print(json.dumps(dict(analysis_id=row_id, claim_verifier_ok=verifier['ok'], trust_gate=raw['trust_gate'],
        push_enabled=push, pushed=False, structured_json_present=True, style_checks=style_check(row['summary_text']),
        external_provider_api_called=json.loads(row['raw_json'])['external_provider_api_called'],
        trade_signal_count=signals, characters=len(SUMMARY)), ensure_ascii=False))


if __name__ == '__main__':
    main()
