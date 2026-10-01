"""Store the local-evidence memo; dry-run unless --write is supplied."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260917 import (
    rows, MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-10-02'
TOKENS = {1034137: 'change_percent=+0.23%', 1034138: 'change_percent=-0.00%',
          1034165: 'value=5.26;', 1034173: 'value=3.08;'}
SUMMARY = '''到了這個美股收盤時點，台灣投資人仍缺少最新一晚的行情確認；較早資料透露的變化，是科技股小幅回升沒有帶動半導體同步走強，資金成本也尚未明顯鬆動。對台灣電子權值與供應鏈，接下來更重要的是上漲能否擴散、獲利能否承接估值。這份判斷偏審慎，不能當成美國週四已收盤行情的結論。

最近能核對的股票行情屬於美國週三：那斯達克百大指數上漲 0.23%，費城半導體指數則幾乎持平、略為下跌。科技指數回升與晶片族群停滯同時出現，說明單靠大型科技股的表現，還不足以判定電子產業全面轉強。這種分歧對台灣尤其重要：先進製程、封裝、設備與伺服器的需求雖有關聯，獲利落點卻不相同，海外指數的小幅上漲不能代替接單與毛利率證據。

利率與信用的背景也沒有提供全面放鬆的訊號。美國週二十年期公債殖利率為 5.26%，高收益債信用利差為 3.08%，兩者都高於各自前次觀察值。公債殖利率影響遠期獲利的折現，信用利差則是企業融資相對公債所需的風險補償；它們分別上移，會讓依賴持續融資的擴張計畫面對更嚴格的回報要求。不過，這些是較早日期的觀察，幅度與水準本身都不足以證明信用危機，更不能當成科技股當晚波動的唯一原因。

傳到台灣，電子業必須同時檢驗需求與估值。若先進製程與伺服器訂單維持韌性，實際獲利可以吸收一部分折現壓力；若只見海外科技股上漲、供應鏈展望卻沒有改善，情緒支撐就比較薄弱。金融業的影響則分成新增資金收益、既有債券評價與避險成本，不能把較高殖利率概括成全產業利多。對資本支出較重的製造業，融資成本與現金回收速度更需要一起看。

目前可見的是較早行情中的科技與半導體分歧，無法量化最新价格已反映多少成長或利率壓力。接下來的再定價取決於行情能否擴散，以及企業獲利是否跟上：若半導體轉強、公債殖利率與信用利差緩和，且供應鏈展望穩健，審慎判斷就應調整；若晶片族群持續落後、融資條件轉緊又伴隨獲利下修，壓力便可能從估值延伸到基本面。最新美股收盤仍待確認，不同日期的觀察只能提供背景，不能拼成同一晚的因果。'''.replace('价格', '價格')


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    cal = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and 'us_close' in allowed_analysis_slots(cal)
    writer = MySqlEventStore(load_settings('.env'))
    cur = writer._cursor()
    assert not rows(cur, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='us_close'", (DAY,))
    events = rows(cur, 'SELECT id,source,title,summary,published_at FROM t_relay_events WHERE id IN (1034137,1034138,1034165,1034173)')
    assert {e['id'] for e in events} == set(TOKENS)
    assert all(TOKENS[e['id']] in e['summary'] for e in events)
    assert not rows(cur, "SELECT id FROM t_market_index_snapshots WHERE trade_date='2026-10-01' AND market_session='close'"), 'New close requires review'
    assert not rows(cur, 'SELECT id FROM t_relay_events WHERE id>1034228 LIMIT 1'), 'New evidence requires review'
    structured = dict(schema_version='codex-market-analysis-v1', confidence='low',
        thesis='較早科技與半導體表現分歧，資金成本仍有約束；最新美股收盤未確認。', evidence_event_ids=list(TOKENS),
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
        evidence_freshness=dict(status='limited', current_us_close_available=False, evidence_dates=['2026-09-29','2026-09-30']))
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
