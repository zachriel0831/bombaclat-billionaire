"""Local evidence-only pre-open memo; dry-run by default."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260917 import (
    rows, MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-10-02'
TOKENS = {1034235: 'change_percent=+0.31%', 1034236: 'change_percent=+1.59%',
          1034263: 'value=5.29;', 1034239: 'value=92.97;'}
SUMMARY = '''今晨盤前的價格訊號，比較接近資金重新給半導體成長期待加分：晶片族群漲幅高於大型科技指數，對台灣電子情緒有支撐。台股基調可偏向審慎樂觀，但最大的未知仍是這份期待能否轉成供應鏈獲利，並抵銷利率與能源成本的約束；海外上漲本身，還不是台灣接單全面改善的證明。

半導體接棒，估值仍要靠獲利承接

美國週四行情中，那斯達克百大指數上漲 0.31%，費城半導體指數上漲 1.59%。半導體相對突出，使台灣先進製程、封裝、設備與伺服器供應鏈更容易承接正面情緒。不過，指數反映的是投資人願意支付的價格，未直接回答訂單何時認列、擴產成本如何分攤。這組漲幅支持電子風險偏好改善的判讀，尚不足以推論整條產業鏈的毛利率都會上升。

資金成本仍是另一條線。美國週三十年期公債殖利率日頻觀察為 5.29%，高於前次觀察。這筆資料比股票行情早，不能用來斷言週四股市上漲時利率也同步走高；它提供的是折現背景。當長期資金成本仍有約束，企業需要更清楚的現金流與獲利成長，才能支撐較高估值。對擴產中的電子業，營收成長與投入資本的回報必須一起看；金融業則要分開評估新增投資收益、既有債券評價與避險成本。

今晨西德州原油期貨報每桶 92.97 美元。這是盤前期貨報價，不等同原油結算價或企業實際採購成本，也不能單憑價格水準判定地緣衝突的方向。若能源價格後續持續上行，運輸、物流與耗能製造會更仰賴成本轉嫁；石化業則要看產品報價能否跟上原料，不能把油價上漲直接當成利潤改善。這條成本線若擴散到通膨，也可能讓市場重新評估利率下降的空間。

眼前價格已呈現科技與半導體同步走強，尚無法確認成長前景已被反映到什麼程度。接下來若台灣電子表現擴散、企業展望與現金流同步改善，且利率和能源壓力緩和，審慎樂觀就更有基礎；若半導體漲勢消退、供應鏈獲利下修，又伴隨資金或能源成本上行，這份偏正面的判斷就需要撤回。海外股價、較早的日頻利率與盤前期貨各有時點，台灣開盤後的成交廣度與資金流向，仍是確認傳導是否成立的重要證據。'''


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    cal = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and 'pre_tw_open' in allowed_analysis_slots(cal)
    store = MySqlEventStore(load_settings('.env'))
    cur = store._cursor()
    assert not rows(cur, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='pre_tw_open'", (DAY,)), 'Existing row requires review'
    events = rows(cur, 'SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (1034235,1034236,1034263,1034239)')
    assert {e['id'] for e in events} == set(TOKENS)
    for event in events:
        assert TOKENS[event['id']] in event['summary']
        assert event['published_at'].startswith('2026-09-30' if event['id'] == 1034263 else '2026-10-01')
    structured = dict(schema_version='codex-market-analysis-v1', confidence='medium',
        thesis='半導體相對走強支持台灣電子情緒，台股審慎樂觀；獲利能否承接估值仍待驗證。',
        evidence_event_ids=list(TOKENS),
        tw_sector_transmission=['電子情緒與獲利兌現', '金融收益與債券評價', '運輸製造能源成本'],
        invalidation=['電子表現擴散且展望穩健、利率能源壓力緩和', '半導體漲勢消退且獲利下修、資金或能源成本上行'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = style_check(SUMMARY)
    assert verifier['ok'] and style['ok'], (verifier, style)
    raw = dict(automation_id='market-analysis-codex-guard-pre-open', generator='codex_automation',
        display_title=DAY, calendar=cal.to_dict(), evidence_event_ids=list(TOKENS),
        claim_verifier=verifier, trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'),
        style_checks=style, external_provider_api_called=False, generated_at=now.isoformat(),
        evidence_freshness=dict(equities='2026-10-01', rates='2026-09-30', oil='2026-10-01T23:09:46+00:00', aggregate_conflict='Prefer original timestamped rates and oil over collector aggregate'))
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
    assert 'stock_watch' not in row['structured_json']
    print(json.dumps(dict(analysis_id=row_id, claim_verifier_ok=verifier['ok'], trust_gate=raw['trust_gate'],
        push_enabled=1, pushed=False, structured_json_present=True, style_checks=style_check(row['summary_text']),
        external_provider_api_called=False, trade_signal_count=signals)))


if __name__ == '__main__':
    main()
