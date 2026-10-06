"""Store a dated Codex memo from local facts; dry-run unless --apply."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260917 import (
    rows, MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-10-07'
FACTS = {
    1034728: ('change_percent=+0.48%', '2026-10-06T22:34:12+00:00'),
    1034729: ('change_percent=+0.34%', '2026-10-06T21:15:59+00:00'),
    1034749: ('value=5.27;', '2026-10-06T00:00:00'),
    1034732: ('value=89.9;', '2026-10-06T23:10:05+00:00'),
}
SUMMARY = '''今天盤前，市場仍在衡量科技成長能否承接偏高的資金成本。海外大型科技與半導體同步上漲，讓台股電子情緒保有支撐；我的基調是中性略偏正面，但最大的未知，是這份支持能否轉成台灣供應鏈的獲利與更廣的參與，而非只反映在少數權值股。今晨油價回升，也使成本壓力仍需放進評價之中。

科技上漲提供方向，獲利決定能走多遠

週二那斯達克百大指數上漲 0.48%，費城半導體指數上漲 0.34%。這個組合支持科技風險偏好仍有韌性的判斷，但半導體並未明顯領先；僅憑這些指數，也不能判定整體市場廣度或晶片訂單已經改善。對台灣先進製程、封裝與伺服器鏈，海外情緒可以影響開盤定價，接下來仍要由接單、產能利用率與毛利率承接。若營收增加卻伴隨成本上升，成長故事對股東現金流的幫助就可能打折。

週二美國十年期公債殖利率為 5.27%。這提供資金成本的水準參考，不能只靠單日數字推算降息機率或最新資金流向。當長期折現率仍有約束，遠期獲利占比較高的電子產業，需要更明確的成長與現金流來支撐評價；擴產企業也要比較投資回報與融資成本。金融業則同時面對債券評價、再投資收益及避險費用，利率變化不會對所有金融公司產生相同效果。

能源的影響從成本表傳進來

今晨亞洲交易時段，西德州原油期貨報每桶 89.9 美元，較前值上漲 0.51%。這是早盤報價，不能當作紐約結算價，也不足以單獨證明供應中斷或地緣情勢升級。若漲勢延續，航空、物流與耗能製造會先面對燃料及運輸成本的考驗；石化業仍要比較產品售價和原料成本，不能把油價方向直接當成利潤方向。若企業轉嫁成本，又可能讓通膨與利率預期更難降溫，間接限制電子評價擴張。

眼前價格已呈現科技與半導體同漲的結果，但尚不能量化市場消化了多少未來獲利。仍可能引發重新定價的，是企業展望、長期資金成本與能源價格能否朝同一個有利方向移動。若台灣電子表現擴散、企業現金流改善，且殖利率與油價回落，中性略偏正面的判斷會更有依據；若半導體轉弱、獲利展望下修，又伴隨利率或能源成本上升，就應撤回海外科技情緒能順利傳導的前提。台灣今天的成交廣度與資金流向，仍須等待開盤後確認。'''


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    cal = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and 'pre_tw_open' in allowed_analysis_slots(cal)
    store = MySqlEventStore(load_settings('.env'))
    cur = store._cursor()
    assert not rows(cur, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='pre_tw_open'", (DAY,)), 'Existing row requires review'
    events = rows(cur, 'SELECT id,source,title,summary,published_at FROM t_relay_events WHERE id IN (1034728,1034729,1034749,1034732)')
    assert {e['id'] for e in events} == set(FACTS)
    for event in events:
        token, stamp = FACTS[event['id']]
        assert token in event['summary'] and event['published_at'] == stamp
    structured = dict(schema_version='codex-market-analysis-v1', confidence='medium',
        thesis='科技與半導體上漲支持台股中性略偏正面，資金與能源成本仍限制評價。',
        evidence_event_ids=list(FACTS),
        tw_sector_transmission=['電子獲利與融資成本', '金融債券評價與再投資收益', '運輸製造能源成本'],
        invalidation=['電子擴散與現金流改善、殖利率油價回落', '半導體轉弱與獲利下修、利率或能源成本上升'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = style_check(SUMMARY)
    assert verifier['ok'] and style['ok'], (verifier, style)
    raw = dict(automation_id='market-analysis-codex-guard-pre-open', generator='codex_automation',
        display_title=DAY, calendar=cal.to_dict(), evidence_event_ids=list(FACTS),
        claim_verifier=verifier, trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'),
        style_checks=style, external_provider_api_called=False, generated_at=now.isoformat(),
        evidence_freshness={str(k): v[1] for k,v in FACTS.items()},
        evidence_limits=['Fresh Tuesday equity and Treasury observations supersede earlier US-close memo context', 'Original Wednesday Asia oil quote used instead of stale aggregate', 'Taiwan opening flows unconfirmed'])
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
