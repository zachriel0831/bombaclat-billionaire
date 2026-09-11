"""Codex-authored local memo; dry-run by default, --write persists."""
import json
import sys
from datetime import datetime, timedelta, timezone

from _tw_close_guard_20260907 import check_text
from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore

DAY = '2026-09-11'
IDS = [898193, 898354, 895440, 895472]
SUMMARY = '''今天收盤確認台股的風險承擔意願繼續下降，金融與航運的局部支撐，仍不足以扭轉電子股普遍承壓的局面。跌幅從盤中低點收斂，只能說市場還有承接，不能據此認定油價與利率帶來的評價壓力已經消化完畢。

盤後報導顯示，加權指數下跌755.64點，收在46,184.85點。台積電收低，半導體、電子零組件與電腦周邊同步走弱，金融和航運則逆勢上漲。這個組合比單看指數更有意義：權值電子牽動大盤方向，其他族群雖提供緩衝，買盤卻還沒有回到科技供應鏈。它反映的是部門間表現分化，尚不足以證明同一批資金已從電子轉進金融或航運。

另一則盤後報導指出，三大法人合計賣超逾千億元，外資及陸資賣超、投信買超。機構資金並非全數同向，但總體淨賣出與指數下跌相互印證，讓「只是盤中情緒波動」的解釋變得較弱。法人買賣超反映股票交易結果，不能直接等同資金匯出台灣；即便如此，今日行情仍缺少機構整體買盤的支持。

海外壓力沿著能源成本和資金價格傳來。今晨報導指出，前一個美國交易日油價上升，費城半導體指數下跌2.66%；另一則報導記錄美國長債標售反應不佳，公債殖利率走高。能源供應風險若維持，通膨壓力就可能限制利率下行空間；長期資金成本偏高，又會提高投資人對科技企業未來獲利的要求。對台灣半導體與大型電子而言，即使產業需求有支撐，也不保證評價可以免受利率影響。這是與今日電子弱勢一致的傳導解釋，並非已證明每一段跌勢都由海外因素造成。

非電子產業也不能只看漲跌貼標籤。航運今天走強，仍須區分運價可能受供應擾動支撐，以及燃油、保險與繞航成本可能侵蝕利潤；塑化下游和運輸業則更依賴成本轉嫁能力。金融的相對強勢也不代表殖利率上升全面有利，利差收入與債券評價可能朝不同方向變動。

收盤已呈現對風險的折價，接下來是否繼續調整，取決於能源供應壓力、長債市場能否穩定，以及法人賣壓是否減輕。若油價與殖利率緩和、電子族群恢復較廣泛承接，並獲機構資金支持，就應撤回「風險承擔持續下降」的判斷；若海外成本壓力不退，電子弱勢延續、局部撐盤也縮小，今天的跌幅收斂就只能視為短暫緩衝。'''
STRUCTURED = dict(schema_version='codex-market-analysis-v1', headline='電子承壓，局部撐盤未扭轉風險折價', thesis='收盤確認風險承擔下降，金融航運局部支撐不足以扭轉電子弱勢。', confidence='medium', sentiment='cautious', evidence=[dict(event_id=i) for i in IDS], tw_sector_transmission=['能源與利率限制電子評價', '航運收入與成本效應需分辨', '金融利差與債券評價可能分歧'], invalidation=['油債壓力緩和、電子廣度改善且法人資金支持'], evidence_limitations=['法人精確總額在報導間略有差異，採逾千億元表述', '產業因果屬條件推論，未使用延伸閱讀作當日事實'])


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and (now.hour, now.minute) >= (15, 30)
    assert 'tw_close' in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings('.env'))
    c = store._cursor()
    c.execute('SELECT id,source,title,summary,published_at FROM t_relay_events WHERE id IN (%s,%s,%s,%s)', tuple(IDS))
    events = [dict(zip(['id', 'source', 'title', 'summary', 'published_at'], r)) for r in c.fetchall()]
    assert len(events) == 4 and all(str(e['published_at']).startswith(DAY) for e in events)
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=STRUCTURED, events_payload=events, market_payload=[])
    style = check_text(SUMMARY)
    assert verifier['ok'] and style['ok'], (verifier, style)
    raw = dict(automation_id='market-analysis-codex-guard-tw-close', generator='codex_automation', display_title=DAY, calendar=calendar.to_dict(), evidence_event_ids=IDS, claim_verifier=verifier, trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'), style_checks=style, external_provider_api_called=False, close_confirmation='confirmed_by_closing_reports')
    print(json.dumps(dict(dry_run=True, claim_verifier=verifier, style_checks=style), ensure_ascii=False))
    if '--write' not in sys.argv:
        return
    c.execute("SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='tw_close'", (DAY,))
    assert c.fetchone() is None, 'Existing row requires review before overwrite'
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(analysis_date=DAY, analysis_slot='tw_close', scheduled_time_local='15:30', model='codex-local-judgment', prompt_version='codex-flexible-briefing-memo-v1', summary_text=SUMMARY, events_used=4, market_rows_used=0, push_enabled=False, pushed=False, raw_json=json.dumps(raw, ensure_ascii=False), structured_json=json.dumps(STRUCTURED, ensure_ascii=False)))
    c.execute('SELECT summary_text,raw_json,structured_json,push_enabled,pushed FROM t_market_analyses WHERE id=%s', (row_id,))
    row = c.fetchone()
    c.execute('SELECT COUNT(*) FROM t_trade_signals WHERE analysis_id=%s', (row_id,))
    signals = c.fetchone()[0]
    assert row[0] == SUMMARY and json.loads(row[1]) == raw and json.loads(row[2]) == STRUCTURED
    assert row[3] == 0 and row[4] == 0 and signals == 0 and check_text(row[0])['ok']
    print(json.dumps(dict(analysis_id=row_id, claim_verifier_ok=verifier['ok'], trust_gate=raw['trust_gate'], push_enabled=row[3], pushed=row[4], structured_json_present=True, style_checks=check_text(row[0]), external_provider_api_called=False, stock_watch_present=False, trade_signal_count=signals)))
    c.close()


if __name__ == '__main__':
    main()
