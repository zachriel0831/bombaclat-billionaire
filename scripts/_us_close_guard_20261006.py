"""Persist a Codex-authored local memo; dry-run unless --apply is supplied."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260917 import (
    rows, MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-10-06'
FACTS = {
    1034530: ('change_percent=+1.00%', '2026-10-02T21:15:59+00:00'),
    1034533: ('value=101.884;', '2026-10-04T23:10:06+00:00'),
    1034534: ('value=91.15;', '2026-10-04T23:10:07+00:00'),
    1034554: ('value=4;', '2026-10-04'),
}
SUMMARY = '''這次美股收盤時點，台灣投資人仍不能確認隔夜行情是否改變科技股的支撐力。可核對的美股價格停在上週五，美元與油價則是週一亞洲早盤，因此今天較合理的判斷，是保留電子產業的成長背景，同時降低對短線方向的信心。週一美股收盤若未確認，就不能把先前漲勢接續寫成新一晚的資金流入，更不能直接推論台股開盤強弱。

先把價格放回各自的時間

上週五那斯達克百大指數上漲 1.00%，支持大型科技股當時受到較高定價的描述。這份背景有利於台灣先進製程、封裝與伺服器供應鏈的市場情緒，但只證明價格變化，並未證明新增訂單或獲利上修。今天仍有意義的問題，是客戶支出與企業現金流能否承接估值；若最新行情已反轉，上週五的情緒支撐就必須重新評估。

週一亞洲早盤美元指數為 101.884，較前值回落 0.05%。當時變動有限，不能據此宣稱美元進入跌勢，也不能推斷外資已流入台灣。若後續美元走弱、台幣及外資流向同步確認，資金環境改善才有較完整的證據。出口企業還須區分收入換算、進口成本與避險效果，本幣升值對各產業的影響不會完全相同。

利率與能源仍是估值之外的約束。週日有效的聯準會政策利率區間上限為 4%，這是既有水準，並非新的政策決定；長天期公債殖利率也不能由政策上限直接推算。週一亞洲早盤西德州原油期貨報每桶 91.15 美元，較前值上漲 0.04%，只足以描述那個時點的報價，不能代表最新紐約結算。缺少後續價格確認，既不能宣布成本壓力解除，也不能斷言隔夜出現新的能源衝擊。

台灣產業的傳導因此要分開看：電子與半導體需要接單及毛利率支撐遠期成長定價；航空、物流與耗能製造更在意燃料成本能否轉嫁；金融業則同時面對債券評價、利差與匯率避險負擔。科技股先前上漲，並不保證這些成本同步下降。

目前能確認的定價背景僅是上週五大型科技走強，無法量化週一市場已反映多少利率與需求變化。若最新科技股強勢擴散、企業展望改善，且美元與能源成本沒有上行，低信心的中性判斷可調整；若科技退潮伴隨展望下修，再遇殖利率或油價上升，就應撤回電子情緒仍有支撐的前提。這份短評保留既有背景，最新一晚股債匯市的方向仍待確認。'''


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    cal = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and 'us_close' in allowed_analysis_slots(cal)
    store = MySqlEventStore(load_settings('.env'))
    cur = store._cursor()
    assert not rows(cur, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='us_close'", (DAY,))
    assert not rows(cur, 'SELECT id FROM t_relay_events WHERE id>1034617 LIMIT 1'), 'New evidence requires review'
    assert not rows(cur, "SELECT id FROM t_market_index_snapshots WHERE trade_date='2026-10-05'"), 'Current session requires review'
    events = rows(cur, 'SELECT id,source,title,summary,published_at FROM t_relay_events WHERE id IN (1034530,1034533,1034534,1034554)')
    assert {e['id'] for e in events} == set(FACTS)
    for e in events:
        token, stamp = FACTS[e['id']]
        assert token in e['summary'] and e['published_at'] == stamp
    structured = dict(schema_version='codex-market-analysis-v1', confidence='low',
        thesis='電子成長背景仍在，但最新美股收盤未確認，方向判斷維持低信心。', evidence_event_ids=list(FACTS),
        tw_sector_transmission=['電子訂單與估值', '運輸製造能源成本', '金融利差與避險負擔'],
        invalidation=['科技強勢擴散且企業展望改善', '科技退潮與展望下修、資金或能源成本上升'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = style_check(SUMMARY)
    assert verifier['ok'] and style['ok'], (verifier, style)
    push = not cal.tw.is_trading_day
    raw = dict(automation_id='market-analysis-codex-guard-us-close', generator='codex_automation',
        display_title=DAY, calendar=cal.to_dict(), evidence_event_ids=list(FACTS), claim_verifier=verifier,
        trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'),
        style_checks=style, external_provider_api_called=False, generated_at=now.isoformat(),
        evidence_freshness={str(k): v[1] for k,v in FACTS.items()},
        evidence_limits=['2026-10-05 US close unconfirmed', 'Friday equity and Monday Asia prices are background only', 'Original oil timestamp used instead of conflicting aggregate'])
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
