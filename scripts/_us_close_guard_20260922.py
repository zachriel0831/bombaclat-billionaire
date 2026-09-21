"""Local-evidence US close memo; dry-run unless --write is supplied."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260917 import (
    rows, MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-09-22'
EVENT_IDS = [982886, 982409, 979908]
MARKET_IDS = [413, 414, 415, 416]
SUMMARY = """這次美股收盤帶給台灣投資人的變化，是風險壓力出現鬆動的空間：標普與道瓊收盤都高於當日開盤，油價回落與美中談判訊息，也讓市場有理由重新衡量能源和貿易風險。對台灣電子供應鏈而言，外部環境暫時朝較有利的方向移動；但目前更像風險溢酬可能下降，還不能直接解讀成資金成本已降低或企業獲利已上修。

先看行情本身。標普收在 7765.10 點，道瓊同樣收高於開盤，表示當日買盤能延續到收市。這提供風險偏好改善的線索，卻不足以證明所有產業同步走強，也無法單靠指數把漲勢歸因於外交消息。台灣若要延續這份正面情緒，仍需電子權值、半導體與更廣泛的市場表現互相確認。

能源是影響較直接的一環。經濟日報在美股盤中報導，油價隨美伊可能會面的期待下跌，沙烏地供貨也可望部分恢復。這是外交與供應改善的預期，尚非停戰或供貨完全恢復的結果，也不能把盤中報價當成結算價。若油價回落能維持，台灣航空、運輸與耗能製造的成本壓力可能減輕，通膨預期也較有降溫空間；石化業則須同時看原料與產品報價，油跌未必代表利潤立即增加。

貿易政策提供另一條傳導。貝森特表示相信對中高關稅休兵會延長，並提及討論 AI 對話機制。對跨境電子供應鏈而言，政策不確定性若下降，可減少客戶延後採購與調整庫存的誘因；但談判訊號不等於新協議生效，更不代表先進晶片的出口限制已解除。因此，台灣先進製程、伺服器與封裝產業的評價可以受情緒改善支持，實際營收仍須回到訂單與出貨驗證。

產業端已有台灣供應鏈與光學業者合作開發 AI 資料中心光學互連的消息，重點在低功耗與低延遲。它說明運算擴張仍在尋找能源效率與傳輸瓶頸的解法，可能把需求傳到光通訊、封裝及相關設備；合作與展示規劃本身，卻不是量產收入或毛利率改善的證據。

眼前行情已顯示股市買盤回升，外交進展究竟被反映多少仍難量化。後續可再定價的是供油能否恢復、貿易安排能否落地，以及成本改善是否轉成獲利。若油價跌勢逆轉、談判受阻，或美元與殖利率重新走強，這份偏正面的判斷就要下修；若能源壓力持續緩和、政策承諾落實，且電子訂單與利潤同步改善，行情才有更扎實的支撐。目前沒有足夠的同時段利率與匯率證據可確認全面寬鬆，美股單晚回升也不等於台股資金已全面回流。"""


def main():
    calendar = resolve_market_calendar_state(datetime.now(timezone(timedelta(hours=8))))
    assert str(calendar.local_date) == DAY and 'us_close' in allowed_analysis_slots(calendar)
    writer = MySqlEventStore(load_settings('.env'))
    cur = writer._cursor()
    assert not rows(cur, "SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='us_close'", (DAY,)), 'Review existing row separately; preserve delivery state'
    events = rows(cur, 'SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (982886,982409,979908)')
    market = rows(cur, 'SELECT id,trade_date,market_session,symbol,recorded_price FROM t_market_index_snapshots WHERE id IN (413,414,415,416)')
    assert {e['id'] for e in events} == set(EVENT_IDS)
    assert {m['id'] for m in market} == set(MARKET_IDS)
    assert all(m['trade_date'] == '2026-09-21' for m in market)
    for symbol in ('DJIA', 'S&P 500'):
        prices = {m['market_session']: float(m['recorded_price']) for m in market if m['symbol'] == symbol}
        assert prices['close'] > prices['open']
    structured = dict(schema_version='codex-market-analysis-v1', confidence='medium',
        thesis='美股回升與能源、貿易風險緩解期待有利台灣電子情緒，仍須政策落地與獲利確認。',
        evidence_event_ids=EVENT_IDS, market_snapshot_ids=MARKET_IDS,
        tw_sector_transmission=['電子供應鏈的政策不確定性', '能源成本傳到運輸與製造', 'AI 傳輸效率需求傳到光通訊與封裝'],
        invalidation=['油價反彈或外交談判受阻', '美元與殖利率走強', '電子訂單及利潤未能確認'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=market)
    style = style_check(SUMMARY)
    assert verifier['ok'] and style['ok'], json.dumps(dict(verifier=verifier, style=style), ensure_ascii=False)
    push = not calendar.tw.is_trading_day
    raw = dict(automation_id='market-analysis-codex-guard-us-close', generator='codex_automation',
        display_title=DAY, calendar=calendar.to_dict(), evidence_event_ids=EVENT_IDS, market_snapshot_ids=MARKET_IDS,
        claim_verifier=verifier, trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'),
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
    assert style_check(row['summary_text'])['ok'] and raw['external_provider_api_called'] is False
    print(json.dumps(dict(analysis_id=row_id, claim_verifier_ok=verifier['ok'], trust_gate=raw['trust_gate'],
        push_enabled=push, pushed=False, structured_json_present=True, style_checks=style_check(row['summary_text']),
        external_provider_api_called=False, trade_signal_count=signals, characters=len(SUMMARY)), ensure_ascii=False))


if __name__ == '__main__':
    main()
