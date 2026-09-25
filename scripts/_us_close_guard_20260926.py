"""Local-only daily memo. Dry-run by default; --write stores an absent row."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260917 import (
    rows, MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-09-26'
EVENT_IDS = [1016073, 1015427]
MARKET_IDS = [427, 428, 429, 430, 431, 432]
SUMMARY = """這次美股收盤讓台灣投資人可以稍微調低對短期風險情緒的戒心，但對資金成本仍需保留審慎。道瓊與標普不僅收在當日開盤之上，也高於前一交易日收盤，回穩因此有了較完整的價格確認。問題是，戰事和解的期待能否轉成能源供應改善，以及美債殖利率上升會不會抵銷這份緩和。台灣週末休市，這些變化要等恢復交易後，才能確認如何反映到本地市場。

先看能源這條線。中央社報導，美伊戰爭可能出現和解契機，國際油價應聲回落，歐股多數收紅。對市場有幫助的是能源風險溢價有機會降低：若原油與航運成本持續回落，企業成本及通膨壓力便可能減輕。不過，這則消息描述的是和解可能性與報導當時的行情，並未證明協議已生效，也不能直接當成原油最終結算。台灣運輸與耗能製造業能否受惠，仍取決於成本下降的持續時間及採購合約如何調整。

美股收盤回升與上述緩和方向相容，卻不足以證明整晚漲勢都由外交消息驅動。指數上漲代表整體價格有所修復，不能據此推論半導體、金融或所有科技公司同步轉強。對台灣電子鏈而言，風險情緒改善可以先降低估值壓力，但後續能否站穩，仍需要訂單、交期與獲利支持。

另一股力量來自債市。經濟日報指出，美國公債殖利率接連攀高，並引述專家對美債與亞洲新興市場利差擴大、可能加劇資本外流的警告。這是區域風險提示，並非台灣外資已經流出的證據。其傳導機制在於美元資產的相對報酬提高，資金對其他市場的風險補償要求可能隨之增加；若台灣也受到影響，電子權值股的估值與企業融資條件便可能承壓。殖利率上升的速度，往往和水準本身同樣值得留意。

台灣產業因此面對兩種不同的檢驗。先進製程、AI伺服器與電子設備鏈，要看需求成長能否抵銷折現率提高；航空、陸運與耗能製造，則要看燃料及原料成本能否真正降低。石化業還需比較產品售價與原料成本的變化，不能只憑油價方向判斷毛利。匯率與資金流是可能的後續傳導，尚不能從海外債市報導直接推算新台幣走勢。

目前收盤價已顯示承接力道，仍可能再定價的是和解的落實程度，以及高殖利率會維持多久。若停火與運輸改善獲得確認，油價壓力持續緩解、殖利率轉穩，且電子需求保持韌性，這次回升就更有延續的基礎；若談判反覆、能源價格再起，或債市壓力伴隨企業獲利下修，對風險情緒的樂觀看法便需要收回。休市期間先把海外反彈視為條件改善，台灣市場是否同樣接受，仍待實際交易驗證。"""


def main():
    calendar = resolve_market_calendar_state(datetime.now(timezone(timedelta(hours=8))))
    assert str(calendar.local_date) == DAY and 'us_close' in allowed_analysis_slots(calendar)
    writer = MySqlEventStore(load_settings('.env'))
    cur = writer._cursor()
    assert not rows(cur, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='us_close'", (DAY,))
    events = rows(cur, 'SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (1016073,1015427)')
    market = rows(cur, 'SELECT id,trade_date,market_session,symbol,recorded_price FROM t_market_index_snapshots WHERE id IN (427,428,429,430,431,432)')
    assert {e['id'] for e in events} == set(EVENT_IDS)
    assert all(e['published_at'][:10] == DAY for e in events)
    assert {m['id'] for m in market} == set(MARKET_IDS)
    for symbol in ('DJIA', 'S&P 500'):
        prices = {(m['trade_date'], m['market_session']): float(m['recorded_price']) for m in market if m['symbol'] == symbol}
        assert prices[('2026-09-25', 'close')] > prices[('2026-09-25', 'open')]
        assert prices[('2026-09-25', 'close')] > prices[('2026-09-24', 'close')]
    structured = dict(schema_version='codex-market-analysis-v1', confidence='medium',
        thesis='美股收復前收，和解期待緩和能源風險，但美債殖利率仍牽制台灣估值與資金條件。',
        evidence_event_ids=EVENT_IDS, market_snapshot_ids=MARKET_IDS,
        tw_sector_transmission=['電子需求與折現率', '運輸及製造成本', '資金流及匯率的條件式影響'],
        invalidation=['和解落實、能源壓力下降且殖利率轉穩', '談判反覆、能源壓力再起或獲利下修'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=market)
    style = style_check(SUMMARY)
    assert verifier['ok'] and style['ok'], (verifier, style)
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
