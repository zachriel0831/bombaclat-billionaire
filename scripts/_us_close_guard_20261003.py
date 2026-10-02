"""Store Codex's local-evidence memo; dry-run unless --write is supplied."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260917 import (
    rows, MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-10-03'
TOKENS = {1034328: 'period_change=29;', 1034329: 'value=4.2;', 1034331: 'yoy=+3.02%'}
SUMMARY = '''這個美股收盤時點，台灣投資人需要重估的，是美國就業動能偏弱時，利率可能鬆動的好處能否抵銷需求風險。九月就業與薪資資料提供了新的判斷依據，但最新一晚的美股收盤、美元與債市反應仍未確認，現在還不能把經濟數字直接寫成市場已經轉向。對台灣電子與出口產業，估值有沒有支撐，必須和客戶需求能否維持分開判斷。

美國勞工統計的九月初值顯示，非農就業較前月增加約兩萬九千人；失業率為 4.2%，較前月上升。新增職位有限、失業率走高，讓成長承受的壓力值得留意。不過，兩者來自不同調查，不能硬湊成同一群人的流動，也不能只靠單月數據宣告衰退。缺少市場事前預期的比較，更無法斷言這次數字是正面還是負面的意外。

薪資則提供另一個角度：九月平均時薪年增 3.02%，且仍高於前月。工資增加可以支撐家庭收入，卻也意味勞動成本並未停止上升。因此，就業放緩可能增加政策轉向寬鬆的理由，但薪資、物價與後续資料仍會制約調整速度；目前不能由這份就業報告推出降息幅度，更不能宣稱融資條件已改善。就業與薪資都是初值，後續修正也可能改變判讀。

台灣面對的是兩條可能方向不同的傳導。若成長放慢使公債殖利率下降，而企業需求保持韌性，先進製程、封裝與伺服器供應鏈的遠期獲利折現壓力有機會減輕；但若就業轉弱逐步壓低消費與企業支出，消費電子、零組件及外銷製造反而可能先面對訂單調整。資料中心投資也需要由客戶預算、訂單與現金流驗證，不能假設利率下降就足以維持所有擴張計畫。金融業則須區分債券評價、利差收益與信用成本，方向未必一致。

眼前能確認的是就業與薪資的數據組合，還無法量化股債價格已反映多少寬鬆期待或需求風險。接下來若殖利率緩和、信用利差穩定，且台灣供應鏈展望沒有轉弱，偏審慎的需求判斷就應調整；若利率下行卻伴隨信用利差擴大、訂單與獲利展望下修，市場面對的可能是成長壓力，而非單純估值改善。若就業數字大幅上修，也必須重看成長偏弱的前提。這份短評以就業資料作為收盤時點的背景，尚不能替最新一晚行情下結論。'''.replace('後续', '後續')


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    cal = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and 'us_close' in allowed_analysis_slots(cal)
    writer = MySqlEventStore(load_settings('.env'))
    cur = writer._cursor()
    assert not rows(cur, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='us_close'", (DAY,))
    events = rows(cur, 'SELECT id,source,title,summary,published_at,raw_json FROM t_relay_events WHERE id IN (1034328,1034329,1034331)')
    assert {e['id'] for e in events} == set(TOKENS)
    for e in events:
        assert TOKENS[e['id']] in e['summary']
        original = json.loads(e['raw_json'])
        assert original['year'] == '2026' and original['period'] == 'M09'
        assert original['generated_at'].startswith(DAY)
    assert not rows(cur, "SELECT id FROM t_market_index_snapshots WHERE trade_date='2026-10-02' AND market_session='close'"), 'New close requires review'
    assert not rows(cur, 'SELECT id FROM t_relay_events WHERE id>1034332 LIMIT 1'), 'New evidence requires review'
    structured = dict(schema_version='codex-market-analysis-v1', confidence='low',
        thesis='就業動能偏弱使寬鬆與需求風險並存；最新收盤市場反應未確認。', evidence_event_ids=list(TOKENS),
        tw_sector_transmission=['電子估值與客戶需求分開驗證', '出口製造訂單與金融信用成本'],
        invalidation=['就業數字上修或供應鏈需求維持韌性', '信用利差擴大且訂單與獲利展望轉弱'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = style_check(SUMMARY)
    assert verifier['ok'] and style['ok'], (verifier, style)
    push = not cal.tw.is_trading_day
    raw = dict(automation_id='market-analysis-codex-guard-us-close', generator='codex_automation', display_title=DAY,
        calendar=cal.to_dict(), claim_verifier=verifier, evidence_event_ids=list(TOKENS),
        trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'),
        style_checks=style, external_provider_api_called=False, generated_at=now.isoformat(),
        evidence_freshness=dict(status='limited', current_us_close_available=False, observation_period='2026-M09',
            collected_date=DAY, published_at_semantics='period_start_not_release_timestamp'))
    print(json.dumps(dict(dry_run='--write' not in sys.argv, verifier=verifier, style=style, push_enabled=push), ensure_ascii=False))
    if '--write' not in sys.argv:
        return
    row_id = writer.upsert_market_analysis(MarketAnalysisRecord(analysis_date=DAY, analysis_slot='us_close',
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
        external_provider_api_called=False, trade_signal_count=signals, characters=len(SUMMARY)), ensure_ascii=False))


if __name__ == '__main__':
    main()
