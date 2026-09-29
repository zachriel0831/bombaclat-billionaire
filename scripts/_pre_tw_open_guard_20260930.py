"""Local evidence-only September 30 pre-open memo; dry-run by default."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260917 import (
    rows, MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-09-30'
TOKENS = {1034038: 'change_percent=+1.32%', 1034043: 'change_percent=+0.90%',
          1034058: 'value=5.26;', 1034041: 'value=89.35;'}
SUMMARY = '''盤前的主線是半導體價格回升與資金成本仍高之間的拉鋸。海外電子行情提供台股情緒支撐，但還不足以證明需求與獲利全面加速，因此對台股維持中性偏審慎。最大的未知，是這份回升能否在台灣開盤後擴散到供應鏈，並由企業利潤接棒，而非只停留在估值修復。

半導體回升，獲利驗證仍在後面

最新隔夜行情顯示，費城半導體指數上漲 1.32%，台積電美國存託憑證上漲 0.90%。兩者同向提供電子權值與半導體產業較有支撐的價格訊號，卻不能單憑漲幅判定訂單增加，更不能把海外股價直接套成台灣現股的開盤幅度。對先進製程、封裝、設備與伺服器供應鏈，真正能延長這份支撐的，是接單落實、交付順利與毛利率穩定；價格回升只是市場願意重新評估的起點。

另一端，美國十年期公債殖利率最新日頻資料為 5.26%。這是殖利率水準，不是今晨突然跳升的幅度，也不是央行政策利率。較高的折現要求意味著，即使營收展望改善，遠期獲利仍需要更強的現金流支持。台灣電子業因此要把需求與估值分開看；金融業則同時面對新增投資收益與既有債券評價的不同影響，還要考慮持有期限和避險成本，不能概括為整個族群受惠。

能源端，今晨西德州原油期貨報每桶 89.35 美元，接近前值。這個盤前報價只能說當下變化有限，不能確認成本壓力已持續消退，也不能由油價推定地緣衝突緩和。對運輸、物流及耗能製造，後续油價若維持平穩，成本不確定性有機會降低，但能否改善利潤仍取決於合約、庫存與售價轉嫁；石化也須看產品價差，不能把原料價格方向直接當作獲利方向。

目前價格已呈現半導體回升，尚待確認的是台灣市場的承接廣度，以及獲利能否抵銷資金成本。若電子表現擴散、企業展望穩健，且殖利率壓力緩和，盤前的審慎程度便可降低；若回升迅速消退、訂單或利潤下修，又伴隨殖利率或油價上行，估值與成本壓力就可能重新主導。海外行情、日頻利率與盤前期貨各有觀察時點，這份判斷不能替代台灣開盤後的成交與資金流向確認。'''.replace('後续', '後續')


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    cal = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and 'pre_tw_open' in allowed_analysis_slots(cal)
    store = MySqlEventStore(load_settings('.env'))
    cur = store._cursor()
    assert not rows(cur, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='pre_tw_open'", (DAY,)), 'Existing row requires review'
    events = rows(cur, 'SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (1034038,1034043,1034058,1034041)')
    assert {e['id'] for e in events} == set(TOKENS)
    for event in events:
        assert TOKENS[event['id']] in event['summary']
        assert event['published_at'].startswith('2026-09-29')
    structured = dict(schema_version='codex-market-analysis-v1', confidence='medium',
        thesis='半導體回升與資金成本拉鋸，台股中性偏審慎；承接廣度及獲利仍待驗證。',
        evidence_event_ids=list(TOKENS),
        tw_sector_transmission=['電子供應鏈需求與估值', '金融收益與債券評價', '運輸製造能源成本'],
        invalidation=['電子表現擴散且展望穩健、利率壓力緩和', '回升消退且獲利下修、利率或油價上行'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = style_check(SUMMARY)
    assert verifier['ok'] and style['ok'], (verifier, style)
    raw = dict(automation_id='market-analysis-codex-guard-pre-open', generator='codex_automation',
        display_title=DAY, calendar=cal.to_dict(), evidence_event_ids=list(TOKENS),
        claim_verifier=verifier, trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'),
        style_checks=style, external_provider_api_called=False, generated_at=now.isoformat())
    print(json.dumps(dict(dry_run='--apply' not in sys.argv, characters=len(SUMMARY), verifier=verifier, style=style)))
    if '--apply' not in sys.argv:
        return
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(analysis_date=DAY, analysis_slot='pre_tw_open',
        scheduled_time_local='07:30', model='codex-local-judgment', prompt_version='codex-flexible-briefing-memo-v1',
        summary_text=SUMMARY, events_used=len(events), market_rows_used=0, push_enabled=True, pushed=False,
        raw_json=json.dumps(raw, ensure_ascii=False), structured_json=json.dumps(structured, ensure_ascii=False)))
    reader = MySqlEventStore(load_settings('.env'))
    rc = reader._cursor()
    row = rows(rc, 'SELECT summary_text,raw_json,structured_json,push_enabled,pushed FROM t_market_analyses WHERE id=%s', (row_id,))[0]
    signals = rows(rc, 'SELECT COUNT(*) n FROM t_trade_signals WHERE analysis_id=%s', (row_id,))[0]['n']
    assert row['summary_text'] == SUMMARY and json.loads(row['raw_json']) == raw and json.loads(row['structured_json']) == structured
    assert row['push_enabled'] == 1 and not row['pushed'] and signals == 0
    print(json.dumps(dict(analysis_id=row_id, claim_verifier_ok=verifier['ok'], trust_gate=raw['trust_gate'],
        push_enabled=1, pushed=False, structured_json_present=True, style_checks=style_check(row['summary_text']),
        external_provider_api_called=False, trade_signal_count=signals)))


if __name__ == '__main__':
    main()
