"""Persist a dated Codex memo from local facts; default is dry-run."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260917 import (
    rows, MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-10-07'
FACTS = {
    1034629: ('change_percent=+0.87%', '2026-10-05T21:15:59+00:00'),
    1034630: ('change_percent=+0.27%', '2026-10-05T21:15:59+00:00'),
    1034650: ('value=5.31;', '2026-10-05T00:00:00'),
    1034633: ('value=89.26;', '2026-10-05T23:09:34+00:00'),
}
SUMMARY = '''這次美股收盤時點，台灣投資人還不能確認隔夜行情是否延續科技股強勢。能核對的美股資料仍停在週一，週二收盤方向尚待確認；因此今天保留電子產業的情緒支撐背景，卻不把它當成台股即將走強的依據。更值得留意的是，科技股上漲與偏高的長期資金成本可以同時存在，台灣供應鏈仍須靠獲利承接估值。

科技走強，半導體的回應較溫和

週一那斯達克百大指數上漲 0.87%，費城半導體指數上漲 0.27%。兩者方向一致，但半導體漲幅較小，至少不能把大型科技股的強勢直接等同整條晶片供應鏈同步加速。這是當日價格表現的差異，並非訂單已經分化的證明。對台灣先進製程、封裝與伺服器產業而言，情緒有背景支撐，實際需求與毛利率則還需要企業展望確認。

週一美國十年期公債殖利率為 5.31%，提供另一個評價基準。只有單日水準，無法判定最新一晚利率升降，也不能據此推算降息機率；但在這樣的折現條件下，遠期成長需要更扎實的現金流支持。若後續殖利率再上行，電子股可能先承受評價壓力，即使接單尚未轉弱。金融業的影響也非單向：利差、債券評價與避險成本，必須分開判斷。

能源端可核對的是週二亞洲早盤西德州原油期貨，每桶 89.26 美元、較前值下跌 0.19%。這不是週二紐約結算價，小幅回落也不足以宣告成本壓力解除。航空、物流與耗能製造仍要看燃料及運輸成本能否持續下降；石化業還需比較產品售價與原料價格，不能只憑油價跌就推定利潤改善。若供應或運輸風險再度推高能源價格，企業成本與通膨預期可能同時受影響，進一步限制估值擴張。

目前能確認已反映在價格中的，是週一科技與半導體同漲但幅度不同；市場究竟消化了多少利率和獲利變化，仍無法量化。後續若半導體強勢擴散、企業展望改善，而殖利率與能源成本回落，低信心的中性判斷就有上修依據。反過來，若科技走勢反轉且獲利展望下修，再疊加資金或燃料成本上升，就應撤回電子情緒仍有支撐的前提。最新一晚股債走勢尚未確認，本文提供的是有日期邊界的背景判讀。'''


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    cal = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and 'us_close' in allowed_analysis_slots(cal)
    store = MySqlEventStore(load_settings('.env'))
    cur = store._cursor()
    assert not rows(cur, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='us_close'", (DAY,))
    assert not rows(cur, 'SELECT id FROM t_relay_events WHERE id>1034716 LIMIT 1'), 'Review new evidence first'
    assert not rows(cur, "SELECT id FROM t_market_index_snapshots WHERE trade_date='2026-10-06'"), 'Review current close first'
    events = rows(cur, 'SELECT id,source,title,summary,published_at FROM t_relay_events WHERE id IN (1034629,1034630,1034650,1034633)')
    assert {e['id'] for e in events} == set(FACTS)
    for e in events:
        token, stamp = FACTS[e['id']]
        assert token in e['summary'] and e['published_at'] == stamp
    structured = dict(schema_version='codex-market-analysis-v1', confidence='low',
        thesis='週一科技強勢仍是背景，週二收盤未確認，電子情緒須由獲利與資金成本共同驗證。',
        evidence_event_ids=list(FACTS), tw_sector_transmission=['電子成長與折現成本', '金融利差與債券評價', '運輸製造能源成本'],
        invalidation=['半導體強勢擴散且展望改善，利率與能源成本回落', '科技反轉與獲利下修，成本上升'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = style_check(SUMMARY)
    assert verifier['ok'] and style['ok'], (verifier, style)
    push = not cal.tw.is_trading_day
    raw = dict(automation_id='market-analysis-codex-guard-us-close', generator='codex_automation', display_title=DAY,
        calendar=cal.to_dict(), evidence_event_ids=list(FACTS), claim_verifier=verifier,
        trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'),
        style_checks=style, external_provider_api_called=False, generated_at=now.isoformat(),
        evidence_freshness={str(k): v[1] for k,v in FACTS.items()},
        evidence_limits=['2026-10-06 US close unconfirmed', 'Monday equities and yields; Tuesday Asia oil are background only'])
    print(json.dumps(dict(dry_run='--apply' not in sys.argv, verifier=verifier, style=style, push_enabled=push, characters=len(SUMMARY)), ensure_ascii=False))
    if '--apply' not in sys.argv:
        return
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(analysis_date=DAY, analysis_slot='us_close',
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
        external_provider_api_called=False, trade_signal_count=signals), ensure_ascii=False))


if __name__ == '__main__':
    main()
