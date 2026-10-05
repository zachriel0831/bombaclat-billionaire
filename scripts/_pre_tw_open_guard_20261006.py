"""Store a dated Codex local-evidence memo; dry-run unless --apply."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260917 import (
    rows, MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-10-06'
FACTS = {
    1034629: ('change_percent=+0.87%', '2026-10-05T21:15:59+00:00'),
    1034630: ('change_percent=+0.27%', '2026-10-05T21:15:59+00:00'),
    1034645: ('change_percent=-0.48%', '2026-10-05T20:00:00+00:00'),
    1034633: ('value=89.26;', '2026-10-05T23:09:34+00:00'),
}
SUMMARY = '''今天盤前，市場仍願意為大型科技成長付出較高價格，但長債走弱提醒我們，資金成本的約束還在。台股基調中性偏正面，電子情緒可承接海外科技股上漲；最大的未知，是這份支持能否擴散到半導體供應鏈與企業獲利，而非只留在大型權值股。今晨油價小幅回落提供一些成本緩衝，尚不足以判定能源風險已經解除。

科技有支撐，擴散力仍待確認

週一那斯達克百大指數上漲 0.87%，費城半導體指數上漲 0.27%。兩者都走高，支持科技風險偏好仍有韌性的判斷；半導體漲幅較小，則使台灣電子全面同步轉強的推論需要保留。這是不同指數之間的表現差異，不能直接當成市場廣度，也不能說成晶片需求下滑。對台灣先進製程、封裝與伺服器鏈，更有意義的驗證是接單、產能利用與毛利率是否跟上，而不是把海外指數漲幅照搬到台股。

與科技股上漲同時，追蹤美國長天期公債的基金下跌 0.48%。長債價格承壓，通常意味長端利率環境對估值較不友善，但單靠基金價格仍無法拆出政策預期、期限溢酬與技術因素各占多少。對擴產中的電子業，成長故事須能覆蓋融資成本；對金融業，新增債券收益與既有部位評價可能朝不同方向變動，不能把利率走高簡化成全體金融業的利多。

能源價格要分清時點

今晨西德州原油期貨報每桶 89.26 美元，較前值回落 0.19%。這個早盤變化只提供有限的成本緩衝，不能直接推論地緣衝突降溫或供應恢復。航空、物流與耗能製造若能維持售價，燃料壓力緩和才可能改善利潤；石化業還須比較產品價格與原料成本。若油價後續反彈，成本轉嫁能力弱的產業會先面對壓力，也可能重新牽動通膨與利率預期。

目前價格已呈現大型科技與半導體走高、長債承壓的組合，尚不能證明市場已充分消化資金成本，也無法由漲幅量化企業未來獲利。若台灣電子表現擴散、企業展望與現金流改善，且長債止穩、能源成本沒有再升，中性偏正面的判斷會更有根據；若半導體轉弱、接單展望下修，又伴隨長債續跌或油價反彈，就應撤回電子情緒可順利傳導的前提。海外行情是盤前背景，今天台灣的成交廣度與資金流向仍須由開盤後確認；早盤油價也不等於紐約結算價。'''


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    cal = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and 'pre_tw_open' in allowed_analysis_slots(cal)
    store = MySqlEventStore(load_settings('.env'))
    cur = store._cursor()
    assert not rows(cur, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='pre_tw_open'", (DAY,)), 'Existing row requires review'
    events = rows(cur, 'SELECT id,source,title,summary,published_at FROM t_relay_events WHERE id IN (1034629,1034630,1034645,1034633)')
    assert {e['id'] for e in events} == set(FACTS)
    for event in events:
        token, stamp = FACTS[event['id']]
        assert token in event['summary'] and event['published_at'] == stamp
    structured = dict(schema_version='codex-market-analysis-v1', confidence='medium',
        thesis='科技上漲支撐台股中性偏正面，但半導體傳導與資金成本仍需確認。',
        evidence_event_ids=list(FACTS),
        tw_sector_transmission=['電子訂單與擴產融資成本', '金融收益與債券評價', '運輸製造能源成本'],
        invalidation=['台灣電子擴散且獲利改善、長債止穩', '半導體與接單轉弱、長債續跌或油價反彈'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = style_check(SUMMARY)
    assert verifier['ok'] and style['ok'], (verifier, style)
    raw = dict(automation_id='market-analysis-codex-guard-pre-open', generator='codex_automation',
        display_title=DAY, calendar=cal.to_dict(), evidence_event_ids=list(FACTS),
        claim_verifier=verifier, trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'),
        style_checks=style, external_provider_api_called=False, generated_at=now.isoformat(),
        evidence_freshness={str(k): v[1] for k,v in FACTS.items()},
        evidence_limits=['Monday original equity and bond quotes available after earlier US-close memo', 'Original Tuesday oil futures quote used instead of conflicting aggregate', 'Taiwan opening flows unconfirmed'])
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
