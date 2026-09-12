"""Local evidence memo. Dry-run by default; --write stores the missing row."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260909 import (
    MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-09-12'
EVENT_IDS = [901451, 900747, 899738]
MARKET_IDS = [387, 388, 391, 392]
SUMMARY = """這次美股收盤給台灣投資人的新訊號，是風險情緒已有修復，但資金成本的壓力還沒有解除。道瓊與標普都高於前一交易日收盤，讓台股電子供應鏈多了一點外部情緒支撐；我的判斷是，這仍比較像壓力之後的反彈，能否延伸成估值回升，要看能源、通膨與資金流是否一起改善。台灣週末休市，海外消息仍可能改變下次開盤面對的條件。

油價是理解這個轉折的一條線索。經濟日報在美股早盤報導油價下跌、股市上漲，與先前能源供應風險帶來的壓力形成反差。若能源成本降溫能延續，企業毛利與消費支出受到的擠壓可能減輕，航空及高耗能製造的成本疑慮也可緩和。但這是早盤消息，不能當成原油結算結果，更不能僅凭股市收高，就認定中東供應與航運風險已經消失。

通膨資料讓這份樂觀需要保留。中央社引述美國勞工部公布的數據，8 月 CPI 年增率維持 3.4%。年增率沒有再上升，不等於物價回落，也不足以保證資金成本很快下降。對台灣先進製程、AI伺服器與電源散熱供應鏈而言，需求成長和估值能否擴張是兩件事：訂單可以支撐獲利，但較高利率仍可能壓低市場願意為遠期獲利付出的價格。後續政策方向還要看通膨細項與央行決策，不能把新聞中的升息預期寫成已定案。

台灣自身的資金訊號也還沒有跟上海外反彈。中央社報導，週五台灣股匯同步走弱，新台幣兌美元收在 31.638 元，並提及外資撤退。這發生在美國通膨公布與美股收盤之前，不能拿來證明外資已對最新結果作出反應；它提醒的是，下次台股開盤仍需確認資金是否回流。台幣走弱可能增加進口能源與原料負擔，出口商的換匯收入則可能受益，實際效果還取決於美元成本和避險安排，不能直接推成電子業全面受惠。

目前價格已反映部分情緒修復，卻看不出市場是否充分消化通膨與政策風險。若油價回落延續、殖利率降溫，且台灣股匯與半導體表現同步改善，這份偏保留的判斷就應轉向更正面；若油價再升、利率壓力不退，或台灣資金持續流出，美股單晚反彈就可能不足以支撐台股估值。接下來真正有辨識力的，是成本與資金條件能否接棒改善，而不是把收紅直接等同於風險解除。""".replace('凭', '憑')


def main():
    calendar = resolve_market_calendar_state(datetime.now(timezone(timedelta(hours=8))))
    assert str(calendar.local_date) == DAY and 'us_close' in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings('.env'))
    cur = store._cursor()
    def rows(sql, params=()):
        cur.execute(sql, params)
        return json.loads(json.dumps([dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()], default=str))
    assert not rows("SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='us_close'", (DAY,))
    events = rows('SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (901451,900747,899738)')
    market = rows('SELECT id,trade_date,market_session,symbol,recorded_price FROM t_market_index_snapshots WHERE id IN (387,388,391,392)')
    assert len(events) == 3 and len(market) == 4
    assert all(e['published_at'].startswith('2026-09-11') for e in events)
    for symbol in ('DJIA', 'S&P 500'):
        prices = {m['trade_date']: float(m['recorded_price']) for m in market if m['symbol'] == symbol}
        assert prices['2026-09-11'] > prices['2026-09-10']
    structured = dict(schema_version='codex-market-analysis-v1', confidence='medium',
        thesis='美股情緒修復，台灣仍待能源與資金條件確認。',
        evidence_event_ids=EVENT_IDS, market_snapshot_ids=MARKET_IDS,
        tw_sector_transmission=['電子估值取決於資金成本', '航空與高耗能製造關注油價', '出口換匯利益須扣除美元成本'],
        invalidation=['油價與殖利率回落且台灣股匯改善', '能源及利率壓力重升、資金持續流出'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=market)
    style = style_check(SUMMARY)
    assert verifier['ok'] and style['ok'], json.dumps(dict(verifier=verifier, style=style))
    raw = dict(automation_id='market-analysis-codex-guard-us-close', generator='codex_automation', display_title=DAY,
        calendar=calendar.to_dict(), evidence_event_ids=EVENT_IDS, market_snapshot_ids=MARKET_IDS,
        claim_verifier=verifier, trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'),
        style_checks=style, external_provider_api_called=False)
    push = not calendar.tw.is_trading_day
    print(json.dumps(dict(dry_run=True, verifier=verifier, style=style, push_enabled=push)))
    if '--write' not in sys.argv:
        return
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(analysis_date=DAY, analysis_slot='us_close',
        scheduled_time_local='05:00', model='codex-local-judgment', prompt_version='codex-flexible-briefing-memo-v1',
        summary_text=SUMMARY, events_used=len(events), market_rows_used=len(market), push_enabled=push, pushed=False,
        raw_json=json.dumps(raw, ensure_ascii=False), structured_json=json.dumps(structured, ensure_ascii=False)))
    row = rows('SELECT * FROM t_market_analyses WHERE id=%s', (row_id,))[0]
    count = rows('SELECT COUNT(*) AS n FROM t_trade_signals WHERE analysis_id=%s', (row_id,))[0]['n']
    assert row['summary_text'] == SUMMARY and json.loads(row['raw_json']) == raw
    assert json.loads(row['structured_json']) == structured and bool(row['push_enabled']) == push
    assert not row['pushed'] and count == 0 and style_check(row['summary_text'])['ok']
    print(json.dumps(dict(analysis_id=row_id, claim_verifier_ok=verifier['ok'], trust_gate=raw['trust_gate'],
        push_enabled=push, pushed=False, structured_json_present=True, style_checks=style,
        external_provider_api_called=False, trade_signal_count=count)))


if __name__ == '__main__':
    main()
