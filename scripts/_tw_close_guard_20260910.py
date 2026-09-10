"""Codex-authored local close memo; dry-run by default, --write persists."""
import json
import sys
from datetime import datetime, timedelta, timezone

from _tw_close_guard_20260907 import check_text
from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore

DAY = '2026-09-10'
IDS = [889608, 890041, 888094, 888093]
SUMMARY = '''今天收盤確認台股的承接力轉弱，沒有確認盤中跌幅收斂已足以扭轉資金退場。指數下跌、量能縮小與法人賣超同時出現，說明市場正在提高持有風險資產的要求；尾盤較低點回穩提供緩衝，卻還不能替整體風險偏好改善背書。

收盤報導顯示，加權指數下跌242.87點、跌幅0.51%，收在46,940.49點。台積電同步收低，被動元件則仍有支撐。權值股牽動指數、局部零組件保留買盤，反映電子內部仍有分化，不能把少數族群的韌性放大成整條科技供應鏈轉強。成交縮量也有兩面性：拋售未必全面加速，但主動承接同樣不足，單看跌幅收斂很容易忽略這個限制。

資金面的訊號更直接。盤後資料指出，台股盤中一度跌逾600點，三大法人合計賣超503.11億元。價格回穩與機構淨賣出並存，較合理的解讀是跌深後仍有承接，尚未看到資金重新擴張風險部位的證據。法人總額無法辨識所有買賣動機，也不能等同資金已匯出台灣，但它足以提醒讀者：今天的反彈幅度與資金支持，需要分開判讀。

外部壓力則沿著能源與利率傳進來。今晨報導指出，前一個美國交易日布蘭特原油期貨收盤突破每桶100美元，背景是荷姆茲海峽航運衝突升高；另一則報導指出，美國公債殖利率走高、美股普遍走弱。這兩條線索共同提高台灣企業與投資人的門檻：油價若維持高位，運輸及下游製造業更需要成本轉嫁能力；利率壓力若持續，半導體與大型電子股的評價就更依賴獲利兑现，而難單靠題材擴張。塑化也須分辨產品售價上升與原料負擔，不能把能源上漲一律視為利多。

這是與今日弱勢一致的傳導路徑，並非已證明台股每一段下跌都由油價或美債造成。收盤價格已呈現風險折價，是否還需進一步調整，取決於能源供應風險會持續多久、利率壓力能否緩和，以及法人賣壓是否延續。目前沒有足夠證據判定這些風險已全數反映。

若後續油價與殖利率壓力緩和、法人賣壓減輕，而且电子權值與零組件的承接能同步擴大，就應撤回「資金支持持續轉弱」的判斷。反過來，若能源衝擊延續、法人持續淨賣出，局部強勢又逐漸收窄，今天的跌幅收斂便更像短暫緩衝。現階段收盤確認的是防守心態升高，全面止穩仍待資金與產業廣度共同證明。'''.replace('兑现', '兌現').replace('电子', '電子')


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now)
    assert now.date().isoformat() == DAY and (now.hour, now.minute) >= (15, 30)
    assert 'tw_close' in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings('.env'))
    c = store._cursor()
    c.execute('SELECT id,source,title,summary,published_at FROM t_relay_events WHERE id IN (%s,%s,%s,%s)', tuple(IDS))
    events = [dict(zip(['id', 'source', 'title', 'summary', 'published_at'], r)) for r in c.fetchall()]
    assert len(events) == 4 and all(str(e['published_at']).startswith(DAY) for e in events)
    structured = dict(schema_version='codex-market-analysis-v1', headline='跌幅收斂，法人賣壓仍限制承接', thesis='收盤確認承接轉弱，尚未確認風險偏好回升。', confidence='medium', sentiment='cautious', evidence=[dict(event_id=i) for i in IDS], tw_sector_transmission=['半導體與大型電子評價受利率限制', '零組件局部承接尚未擴散', '運輸與下游製造成本轉嫁'], invalidation=['油價與殖利率緩和、法人賣壓減輕且電子承接擴大'], evidence_limitations=['海外收盤與台股收盤時間不同', '法人淨賣出不能等同跨境匯出或確定因果'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = check_text(SUMMARY)
    assert verifier['ok'] and style['ok'], (verifier, style)
    raw = dict(automation_id='market-analysis-codex-guard-tw-close', generator='codex_automation', display_title=DAY, calendar=calendar.to_dict(), evidence_event_ids=IDS, claim_verifier=verifier, trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'), style_checks=style, external_provider_api_called=False, close_confirmation='confirmed_by_closing_reports')
    print(json.dumps(dict(dry_run=True, claim_verifier=verifier, style_checks=style), ensure_ascii=False))
    if '--write' not in sys.argv:
        return
    c.execute("SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='tw_close'", (DAY,))
    assert c.fetchone() is None, 'Existing row requires review before overwrite'
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(analysis_date=DAY, analysis_slot='tw_close', scheduled_time_local='15:30', model='codex-local-judgment', prompt_version='codex-flexible-briefing-memo-v1', summary_text=SUMMARY, events_used=4, market_rows_used=0, push_enabled=False, pushed=False, raw_json=json.dumps(raw, ensure_ascii=False), structured_json=json.dumps(structured, ensure_ascii=False)))
    c.execute('SELECT summary_text,raw_json,structured_json,push_enabled,pushed FROM t_market_analyses WHERE id=%s', (row_id,))
    row = c.fetchone()
    c.execute('SELECT COUNT(*) FROM t_trade_signals WHERE analysis_id=%s', (row_id,))
    signals = c.fetchone()[0]
    assert row[0] == SUMMARY and json.loads(row[1]) == raw and json.loads(row[2]) == structured
    assert row[3] == 0 and row[4] == 0 and signals == 0 and check_text(row[0])['ok']
    print(json.dumps(dict(analysis_id=row_id, claim_verifier_ok=verifier['ok'], trust_gate=raw['trust_gate'], push_enabled=row[3], pushed=row[4], structured_json_present=True, style_checks=check_text(row[0]), external_provider_api_called=False, stock_watch_present=False, trade_signal_count=signals)))
    c.close()


if __name__ == '__main__':
    main()
