"""Store Codex-authored local evidence memo; dry-run by default."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260917 import (
    rows, MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-10-05'
FACTS = {
    1034530: ('change_percent=+1.00%', '2026-10-02T21:15:59+00:00'),
    1034533: ('value=101.884;', '2026-10-04T23:10:06+00:00'),
    1034534: ('value=91.15;', '2026-10-04T23:10:07+00:00'),
    1034554: ('value=4;', '2026-10-04'),
}
SUMMARY = '''新一週盤前，市場仍在衡量科技成長期待能否承接資金與能源成本。週五美國大型科技股走強，對台灣電子情緒提供正面背景；今晨美元與油價變動不大，暫時不足以改寫這個方向。台股基調偏中性、電子情緒略有支撐，最大的未知是海外價格訊號能否轉成台灣開盤後的資金擴散與企業獲利，而非只集中在少數權值股。

科技期待帶過週末，仍要等台灣市場確認

週五那斯達克百大指數上漲 1.00%，代表大型科技股在週末前獲得較高定價。這有利於台灣先進製程、封裝與伺服器供應鏈承接情緒，但指數漲幅不能直接當成新增訂單或毛利率改善。美國週日沒有新的股票收盤，這份支持來自週五行情，不能說成昨夜美股又漲了一輪。今天更有意義的驗證，是電子表現能否擴散，以及企業展望能否承接市場對成長的期待。

今晨美元指數報 101.884，較前值小幅回落 0.05%。這個幅度只支持美元暫時平穩的描述，還不足以推論國際資金大舉流入台股。若美元持續轉弱且台幣與外資流向同步確認，台灣資產的資金環境才更有改善依據；對出口製造業，匯率也會影響收入換算與避險成本，不能把本幣升值一概視為獲利利多。

資金成本並未因科技股上漲而消失。週日有效的聯準會政策利率區間上限為 4%，這是既有政策水準，不是週末新增的利率決定，也不能拿來判定長天期公債殖利率當下的方向。台灣電子業的擴產回報仍須和融資成本一起評估；金融業則要分開看新增投資收益、債券評價與匯率避險負擔。

能源方面，今晨西德州原油期貨報每桶 91.15 美元，較前值上漲 0.04%。早盤變化有限，既不證明供應風險解除，也不足以斷言新的能源衝擊。若油價後續持續上行，航空、物流與耗能製造的成本轉嫁能力會更關鍵；石化業仍要比較產品售價與原料成本，不能單靠油價方向判讀利潤。

目前可確認的定價，是週五大型科技走強與今晨美元、油價相對平穩；市場究竟已反映多少獲利成長，仍無法由這些價格單獨回答。若台灣電子強勢擴散、接單與現金流改善，且資金和能源成本沒有上行，偏中性的判斷可轉積極；若漲勢集中後退潮、企業展望下修，又遇美元或油價走高，就要撤回電子情緒略有支撐的看法。週末後的早盤報價仍可能變動，今天的成交廣度與資金流向比直接沿用海外漲幅更能確認傳導。'''


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    cal = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and 'pre_tw_open' in allowed_analysis_slots(cal)
    store = MySqlEventStore(load_settings('.env'))
    cur = store._cursor()
    assert not rows(cur, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='pre_tw_open'", (DAY,)), 'Existing row requires review'
    events = rows(cur, 'SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (1034530,1034533,1034534,1034554)')
    assert {e['id'] for e in events} == set(FACTS)
    for event in events:
        token, stamp = FACTS[event['id']]
        assert token in event['summary'] and event['published_at'] == stamp
    structured = dict(schema_version='codex-market-analysis-v1', confidence='medium',
        thesis='台股中性、電子情緒略受週五科技行情支撐；資金擴散與獲利傳導待確認。',
        evidence_event_ids=list(FACTS),
        tw_sector_transmission=['電子成長與擴產回報', '金融收益與匯率避險', '運輸製造能源成本'],
        invalidation=['電子擴散且現金流改善、成本穩定', '企業展望下修、科技退潮且美元或油價走高'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = style_check(SUMMARY)
    assert verifier['ok'] and style['ok'], (verifier, style)
    raw = dict(automation_id='market-analysis-codex-guard-pre-open', generator='codex_automation',
        display_title=DAY, calendar=cal.to_dict(), evidence_event_ids=list(FACTS),
        claim_verifier=verifier, trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'),
        style_checks=style, external_provider_api_called=False, generated_at=now.isoformat(),
        evidence_freshness={str(k): v[1] for k, v in FACTS.items()},
        evidence_limits=['Friday equity background, no Sunday US close row used', 'Original timestamped oil used instead of conflicting aggregate', 'Taiwan opening flows unconfirmed'])
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
