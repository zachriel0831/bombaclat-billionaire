"""Store the local-evidence memo; dry-run unless --write is supplied."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260917 import (
    rows, MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-10-01'
TOKENS = {1034038: 'change_percent=+1.32%', 1034043: 'change_percent=+0.90%',
          1034065: 'value=5.24;', 1034073: 'value=3.02;'}
SUMMARY = '''對台灣投資人而言，這個美股收盤時點還不足以確認隔夜風險偏好轉強；能確認的是，較早一個交易日的半導體反彈，並未消除資金成本的約束。台灣電子供應鏈接下來要辨別的，是需求改善能否支撐獲利，而非只把海外股價回升當成估值全面上修的理由。最新美股收盤尚待確認，因此以下判斷偏審慎，談的是傳導條件，不是昨夜行情的定論。

較新的半導體行情屬於美國週二：費城半導體指數上漲 1.32%，台積電美國存託憑證上漲 0.90%。產業指數與大型晶圓製造企業同向回升，至少比各走各路更有利於支撐產業信心；但單日價格變化不能證明訂單或毛利率已經改善，也不能直接推論週三延續漲勢。對先進製程、封裝、設備與伺服器供應鏈，海外價格提供的是情緒參考，真正能延長支撐的仍是接單、交付與現金流。

利率與信用資料提醒我們，反彈還有另一面。最近可核對的美國週一十年期公債殖利率為 5.24%，美國高收益債信用利差為 3.02%。兩者分別代表公債利率水準與信用風險補償，不能混為同一種利率，也不是最新一晚的變化。前者影響遠期獲利的折現，後者反映企業相對於公債的融資條件；僅凭這些水準不足以宣告信用危機，卻說明股票回升不能取代對資金成本的檢驗。

傳到台灣，電子業可能同時面對需求敘事回暖與估值門檻偏高。台積電可作為大型製造業的傳導例子，但海外股價不是台灣現股的預告，更不是整條供應鏈獲利同步改善的證明。若企業擴產需要持續融資，利率與信用條件就會影響成長轉為現金流的速度。金融業則須分開看新增資金收益、既有債券評價與避險成本，不能把公債殖利率較高直接解讀為整個產業受惠。

目前較早行情已呈現半導體回升，尚無足夠證據判斷最新價格反映了多少需求改善或利率壓力。後續再定價取決於反彈是否擴散，以及獲利能否承接估值：若新的半導體行情持續改善、公債殖利率與信用利差緩和，企業展望又保持韌性，審慎判斷就應調整；若反彈消退、信用利差擴大並伴隨獲利下修，壓力便可能從估值延伸到基本面。不同日期的價格與利率只適合提供背景，不能拼成同一晚的市場因果。'''.replace('凭', '憑')


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    cal = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and 'us_close' in allowed_analysis_slots(cal)
    writer = MySqlEventStore(load_settings('.env'))
    cur = writer._cursor()
    assert not rows(cur, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='us_close'", (DAY,))
    events = rows(cur, 'SELECT id,source,title,summary,published_at FROM t_relay_events WHERE id IN (1034038,1034043,1034065,1034073)')
    assert {e['id'] for e in events} == set(TOKENS)
    assert all(TOKENS[e['id']] in e['summary'] for e in events)
    assert not rows(cur, "SELECT id FROM t_market_index_snapshots WHERE trade_date='2026-09-30' AND market_session='close'"), 'New close requires review'
    assert not rows(cur, 'SELECT id FROM t_relay_events WHERE id>1034125 LIMIT 1'), 'New evidence requires review'
    structured = dict(schema_version='codex-market-analysis-v1', confidence='low',
        thesis='較早半導體反彈仍受資金成本約束；最新美股收盤未確認。', evidence_event_ids=list(TOKENS),
        tw_sector_transmission=['電子需求與估值分開檢驗', '金融收益、債券評價及避險成本'],
        invalidation=['半導體改善擴散、利率與信用利差緩和且企業展望穩健', '反彈消退且信用利差擴大、獲利下修'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = style_check(SUMMARY)
    assert verifier['ok'] and style['ok'], (verifier, style)
    push = not cal.tw.is_trading_day
    raw = dict(automation_id='market-analysis-codex-guard-us-close', generator='codex_automation', display_title=DAY,
        calendar=cal.to_dict(), claim_verifier=verifier, evidence_event_ids=list(TOKENS),
        trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'),
        style_checks=style, external_provider_api_called=False, generated_at=now.isoformat(),
        evidence_freshness=dict(status='limited', current_us_close_available=False, evidence_dates=['2026-09-28','2026-09-29']))
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
