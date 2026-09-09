"""Codex-authored close memo; dry-run by default, --write persists."""
import json
import sys
from datetime import datetime, timedelta, timezone

from _tw_close_guard_20260907 import check_text
from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore

DAY = '2026-09-09'
IDS = [881121, 881364, 881608, 879458]
SUMMARY = '''今天收盤確認台股仍有資金承接，卻沒有確認早盤強攻能延續到終場。指數小漲與法人買超並存，但盤中漲勢大幅收斂，較合理的解讀是高檔換手與類股輪動；單憑收紅，還不足以認定整體風險偏好已全面回升。

中央社收盤資料顯示，加權指數收47,183.36點，上漲77.58點，漲幅0.16%，成交金額7,735.06億元。盤後報導則指出，早盤在電子權值帶動下一度上漲超過442點，之後隨台積電轉弱而一度翻黑，尾盤才回到小漲。這段落差比最後的紅黑更有訊息：市場願意承接，卻未能把早盤的樂觀預期留到收盤，權值股對指數的拉動仍不穩定。

資金面提供另一個角度。三大法人合計買超220.81億元，其中外資及陸資、投信買超，自營商賣超。這支持機構資金仍有淨流入，但不同法人並未同向，也不能從總額推定資金全數流向電子。搭配盤後所見面板、光學與塑化較強、金融偏弱，今天更像資金在產業間重新分配，而非所有風險資產一起上修評價。法人買超能與漲勢回吐同時發生，正說明承接力與追價意願需要分開判讀。

能源則是這種分化背後值得保留的限制。上午報導指出，布蘭特原油盤中一度逼近99.7美元；這是早盤油價線索，並非與台股收盤同步的報價。若能源成本維持高位，台灣運輸與下游製造業的利潤會更依賴成本轉嫁能力，塑化也須分辨產品售價改善與原料負擔，不能把油價上漲一律當成利多。對半導體與電子零組件而言，需求期待仍可支撐局部行情，但若通膨壓力使市場降低對利率下行的期待，成長股評價就更需要獲利兌現支撐。這是可能的傳導路徑，不能據此斷言今天回吐全由油價造成。

收盤價格已呈現「有承接、難追價」的拉鋸。接下來仍能改變定價的，是法人淨流入能否延續、電子權值能否把強勢保留到尾盤，以及輪動能否擴展成更穩定的上漲廣度。若買盤延續且金融與電子承接同步改善，今天偏分化的判斷就應上修；若法人轉為淨賣出、尾盤再度失守盤中漲勢，或能源成本升高同時壓縮產業利潤預期，則連目前的承接韌性也需要重新評估。今日收盤支持的是資金尚未全面退場，全面轉強仍需後續行情證明。'''


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now)
    assert now.date().isoformat() == DAY and (now.hour, now.minute) >= (15, 30)
    assert 'tw_close' in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings('.env'))
    c = store._cursor()
    c.execute('SELECT id,source,title,summary,published_at FROM t_relay_events WHERE id IN (%s,%s,%s,%s)', tuple(IDS))
    events = [dict(zip(['id','source','title','summary','published_at'], r)) for r in c.fetchall()]
    assert len(events) == 4 and all(str(e['published_at']).startswith(DAY) for e in events)
    structured = dict(schema_version='codex-market-analysis-v1', headline='法人承接仍在，早盤強勢未能留到收盤', thesis='收盤確認資金承接，但未確認全面風險偏好回升。', confidence='medium', sentiment='neutral', evidence=[dict(event_id=i) for i in IDS], tw_sector_transmission=['電子權值承接與零組件輪動','運輸與下游製造成本轉嫁','塑化產品報價與原料成本拉鋸'], invalidation=['法人買盤延續且金融電子承接同步改善','法人轉賣與尾盤回吐','能源成本升高壓縮利潤預期'], evidence_limitations=['早盤油價與台股收盤時間不同','法人總額不能推定電子部位流向'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = check_text(SUMMARY)
    assert verifier['ok'] and style['ok'], (verifier, style)
    raw = dict(automation_id='market-analysis-codex-guard-tw-close', generator='codex_automation', display_title=DAY, calendar=calendar.to_dict(), evidence_event_ids=IDS, claim_verifier=verifier, trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'), style_checks=style, external_provider_api_called=False, close_confirmation='confirmed_by_closing_reports')
    print(json.dumps(dict(dry_run=True, claim_verifier=verifier, style_checks=style), ensure_ascii=False))
    if '--write' not in sys.argv:
        return
    c.execute("SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='tw_close'", (DAY,))
    assert c.fetchone() is None, 'Existing row requires review before overwrite'
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(analysis_date=DAY, analysis_slot='tw_close', scheduled_time_local='15:30', model='codex-local-judgment', prompt_version='codex-flexible-briefing-memo-v1', summary_text=SUMMARY, events_used=4, market_rows_used=0, push_enabled=False, pushed=False, raw_json=json.dumps(raw,ensure_ascii=False), structured_json=json.dumps(structured,ensure_ascii=False)))
    c.execute('SELECT summary_text,raw_json,structured_json,push_enabled,pushed FROM t_market_analyses WHERE id=%s',(row_id,))
    row = c.fetchone()
    c.execute('SELECT COUNT(*) FROM t_trade_signals WHERE analysis_id=%s',(row_id,))
    signals = c.fetchone()[0]
    assert row[0] == SUMMARY and json.loads(row[1]) == raw and json.loads(row[2]) == structured
    assert row[3] == 0 and row[4] == 0 and signals == 0 and check_text(row[0])['ok']
    print(json.dumps(dict(analysis_id=row_id, claim_verifier_ok=verifier['ok'], trust_gate=raw['trust_gate'], push_enabled=row[3], pushed=row[4], structured_json_present=True, style_checks=check_text(row[0]), external_provider_api_called=False, stock_watch_present=False, trade_signal_count=signals)))
    c.close()


if __name__ == '__main__':
    main()
