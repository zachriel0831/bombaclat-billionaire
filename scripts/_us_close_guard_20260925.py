"""Local evidence memo; dry-run first, --write only for the missing daily row."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260917 import (
    rows, MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-09-25'
EVENT_IDS = [1007459, 1006955, 1007730]
SUMMARY = """這次美股收盤對台灣投資人的提醒，是盤中回穩還不足以解除能源與利率對估值的壓力。道瓊與標普都收在當日開盤之上，卻仍低於前一交易日收盤，較適合解讀為跌勢中的修復，不能直接當成風險偏好全面轉強。台股今天中秋休市，海外消息會繼續累積；下一次開市面對的，可能已是新的油價與政策預期組合。

經濟日報報導，葉門青年運動對沙烏地阿拉伯發動飛彈攻擊，供應受阻的擔憂推動國際油價上漲約3%。這個幅度是報導當時的市場狀態，不能視為所有油種的最終結算。對台灣而言，關鍵是風險溢價會停留多久：短暫跳升先影響市場情緒，持續高檔才可能逐步壓到燃料、物流與原料成本，並延後通膨降溫。

另一則經濟日報報導指出，美國商業活動偏強、通膨壓力增加，加上聯準會官員偏鷹談話，交易員提高對再次升息的押注。這是利率預期，並非下一次決策已經確定。需求強勁原本有利企業收入，但若同時使資金成本維持高檔，成長產業的估值就未必跟著上修。能源衝擊與利率預期若互相強化，台灣電子供應鏈需要用更扎實的獲利，才能抵銷折現率提高的壓力。

局勢也有反向訊號。經濟日報引述消息人士稱，美伊正在討論分階段終戰路線圖，包括重啟荷莫茲海峽及結束封鎖。談判消息可以先降低市場對最壞情境的擔心，但討論方案不等於協議生效，更不等於航運與供應已恢復。這也是為何不能只用一次盤中反彈，推論能源風險已經消失；真正能改變成本預期的，是協議執行及實際運輸改善。

傳到台灣，先進製程、AI伺服器與電子設備鏈首先面對的是估值要求，其次才是客戶資本支出是否因融資成本而遞延。產業需求仍須用訂單、交期與毛利率驗證，不能從美股指數直接推算。航空、陸運與耗能製造對燃料價格更敏感；石化業則要看產品售價能否追上原料成本，不能把油價上漲一律解讀為獲利改善。美元若因利差預期走強，還可能透過換匯成本與外資資金流增加波動，但這仍是後續條件，而非本次已確認的匯率結果。

眼前行情呈現盤中承接，前收比較卻仍偏弱；價格反映了多空拉扯，尚不足以證明風險已充分消化。後續可能再定價的是能源壓力的持續時間，以及市場對緊縮政策的判斷。若談判落實、供應改善帶動油價回落，利率預期轉穩且電子需求保持韌性，審慎看法就應調整；若攻擊與運輸阻礙延續，並伴隨企業成本上升或獲利下修，壓力便可能由評價延伸到營運。休市期間宜把這些變化看成累積中的資訊，台灣市場的實際反應仍待恢復交易後確認。"""


def main():
    calendar = resolve_market_calendar_state(datetime.now(timezone(timedelta(hours=8))))
    assert str(calendar.local_date) == DAY and 'us_close' in allowed_analysis_slots(calendar)
    writer = MySqlEventStore(load_settings('.env'))
    cur = writer._cursor()
    assert not rows(cur, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='us_close'", (DAY,))
    events = rows(cur, 'SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (1007459,1006955,1007730)')
    market = rows(cur, 'SELECT id,trade_date,market_session,symbol,recorded_price FROM t_market_index_snapshots WHERE id IN (425,426,427,428)')
    assert {e['id'] for e in events} == set(EVENT_IDS)
    assert all(e['published_at'][:10] == DAY for e in events)
    assert len(market) == 4 and all(m['trade_date'] == str(calendar.us_close_session_date) for m in market)
    for symbol in ('DJIA', 'S&P 500'):
        prices = {m['market_session']: float(m['recorded_price']) for m in market if m['symbol'] == symbol}
        assert prices['close'] > prices['open']
    previous = rows(cur, 'SELECT id,trade_date,market_session,symbol,recorded_price FROM t_market_index_snapshots WHERE id IN (423,424)')
    assert len(previous) == 2 and all(m['trade_date'] == '2026-09-23' for m in previous)
    for prior in previous:
        close = next(m for m in market if m['symbol'] == prior['symbol'] and m['market_session'] == 'close')
        assert float(close['recorded_price']) < float(prior['recorded_price'])
    market += previous
    structured = dict(schema_version='codex-market-analysis-v1', confidence='medium',
        thesis='美股盤中回穩仍未收復前收，能源與升息預期牽動台灣休市後估值及成本。',
        evidence_event_ids=EVENT_IDS, market_snapshot_ids=[423,424,425,426,427,428],
        tw_sector_transmission=['電子估值與獲利', '運輸與耗能製造成本', '石化產品原料價差'],
        invalidation=['油價回落、殖利率趨穩且電子需求維持韌性', '能源及利率壓力延續並伴隨獲利下修'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=market)
    style = style_check(SUMMARY)
    assert verifier['ok'] and style['ok'], (verifier, style)
    push = not calendar.tw.is_trading_day
    raw = dict(automation_id='market-analysis-codex-guard-us-close', generator='codex_automation',
        display_title=DAY, calendar=calendar.to_dict(), evidence_event_ids=EVENT_IDS,
        market_snapshot_ids=[423,424,425,426,427,428], claim_verifier=verifier,
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
