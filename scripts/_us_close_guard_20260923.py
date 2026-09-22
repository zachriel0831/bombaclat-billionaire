"""Local-evidence memo; dry-run by default and independent readback after --write."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260917 import (
    rows, MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-09-23'
EVENT_IDS = [992075, 991766, 990981]
MARKET_IDS = [417, 418, 419, 420]
SUMMARY = """這次美股收盤帶給台灣投資人的提醒，是能源風險緩解與股市風險偏好回升，還沒有走在同一條路上。原油收低、外交接觸增加，確實讓企業成本有改善的空間；但道瓊與標普都收在當日開盤之下，柴油供應壓力也未解除。對台灣而言，較合理的判斷是成本壓力可能局部鬆動，電子估值與整體資金環境則仍待確認。

行情先提供了一個界線：標普收在 7764.83 點，低於當日開盤，道瓊也呈現同樣方向。這只能說明開盤後的表現偏弱，不能直接當成相對前一交易日的跌幅，更不足以斷定所有產業同步轉差。它的意義在於，即使能源消息轉暖，股市仍未出現足以確認全面風險偏好改善的訊號；台灣半導體與電子權值的評價，不能只靠油價回落就推定會擴張。

自由時報的收盤報導指出，市場評估沙烏地輸油管線重啟與中東局勢後，國際油價收低。經濟日報另引述川普稱，美伊官員在紐約會談具有成效。前者涉及供應替代路徑，後者提供外交緩和的期待，兩者都可能降低能源供應中斷的風險溢酬。不過，管線重啟的報導不等於海峽航運已完全恢復，對會談的正面表述也不是停戰協議；後續實際供油與航運，才是成本改善能否延續的關鍵。

值得對照的是，同一晚經濟日報仍報導全球柴油價格創高，並指出短缺可能延續到明年。這是報導中的展望，不能當成已確定的供需結果，卻提醒原油與成品油不一定同步降價。即使原油走低，煉製與運輸環節若仍緊張，物流及製造成本未必立即下降，通膨也不會自動回到穩定軌道。因此，不能僅憑油價下跌便推導出降息已近或資金成本已降低。

傳到台灣，航空、陸運與耗能製造各自使用的燃料及合約不同，成本改善速度可能分歧；石化業則須看產品報價相對原料的價差。先進製程、AI 伺服器與相關設備鏈更需要拆開需求和估值：能源緩和可改善營運環境，但訂單、毛利率與客戶資本支出才決定獲利，美元和殖利率則會影響市場願意給多少評價。目前的收盤證據尚不足以確認這些條件已一起改善。

眼前價格已呈現原油回落，外交利多究竟反映多少仍難量化。接下來能再定價的，是供應恢复是否落實、成品油壓力能否跟著下降，以及成本改善是否轉成企業利潤。若航運恢復、柴油緊張緩和，且電子訂單與獲利保持韌性，這份審慎判斷就應轉向較正面；若談判受挫、能源再漲，或美元與殖利率重新走強，台灣企業可能再度同時面對成本與估值壓力。美股單晚的盤面仍不能替代台股開盤後的成交與資金流向確認。""".replace('恢复', '恢復')


def main():
    calendar = resolve_market_calendar_state(datetime.now(timezone(timedelta(hours=8))))
    assert str(calendar.local_date) == DAY and 'us_close' in allowed_analysis_slots(calendar)
    writer = MySqlEventStore(load_settings('.env'))
    cur = writer._cursor()
    assert not rows(cur, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='us_close'", (DAY,)), 'Existing row requires separate review'
    events = rows(cur, 'SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (992075,991766,990981)')
    market = rows(cur, 'SELECT id,trade_date,market_session,symbol,recorded_price FROM t_market_index_snapshots WHERE id IN (417,418,419,420)')
    assert {e['id'] for e in events} == set(EVENT_IDS) and {m['id'] for m in market} == set(MARKET_IDS)
    assert all(e['published_at'][:10] == DAY for e in events)
    assert all(m['trade_date'] == str(calendar.us_close_session_date) for m in market)
    for symbol in ('DJIA', 'S&P 500'):
        prices = {m['market_session']: float(m['recorded_price']) for m in market if m['symbol'] == symbol}
        assert prices['close'] < prices['open']
    structured = dict(schema_version='codex-market-analysis-v1', confidence='medium',
        thesis='原油緩和未同步轉成股市與成品油成本改善，台灣產業須分別驗證成本、獲利與估值。',
        evidence_event_ids=EVENT_IDS, market_snapshot_ids=MARKET_IDS,
        tw_sector_transmission=['運輸與耗能製造的燃料成本分歧', '石化產品與原料價差', '電子需求及利率折現分開驗證'],
        invalidation=['航運及柴油供應改善且電子獲利有韌性', '談判受挫或能源再漲', '美元與殖利率走強'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=market)
    style = style_check(SUMMARY)
    assert verifier['ok'] and style['ok'], json.dumps(dict(verifier=verifier, style=style), ensure_ascii=False)
    push = not calendar.tw.is_trading_day
    raw = dict(automation_id='market-analysis-codex-guard-us-close', generator='codex_automation',
        display_title=DAY, calendar=calendar.to_dict(), evidence_event_ids=EVENT_IDS, market_snapshot_ids=MARKET_IDS,
        claim_verifier=verifier, trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'),
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
    assert style_check(row['summary_text'])['ok'] and json.loads(row['raw_json'])['external_provider_api_called'] is False
    print(json.dumps(dict(analysis_id=row_id, claim_verifier_ok=verifier['ok'], trust_gate=raw['trust_gate'],
        push_enabled=push, pushed=False, structured_json_present=True, style_checks=style_check(row['summary_text']),
        external_provider_api_called=False, trade_signal_count=signals, characters=len(SUMMARY)), ensure_ascii=False))


if __name__ == '__main__':
    main()
