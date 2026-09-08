"""Local-only briefing; dry-run by default, --apply stores the missing row."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260909 import style_check
from event_relay.config import load_settings
from event_relay.service import MarketAnalysisRecord, MySqlEventStore
from event_relay.claim_verifier import verify_claim_coverage
from event_relay.market_calendar import resolve_market_calendar_state, allowed_analysis_slots

DAY = '2026-09-09'
IDS = [878510, 878509, 878513, 878530]
SUMMARY = '''市場眼前交易的是半導體的相對韌性，能否抵住能源成本與資金成本的雙重壓力。我對台股盤前的判斷是中性、偏向電子撐盤與類股分化；最大不確定性在於油價壓力會維持多久，以及它是否進一步拖慢通膨降溫、壓縮企業利潤。半導體有支撐，與整體風險偏好全面回升，仍是兩件需要分別驗證的事。

## 電子提供支點，成本限制想像空間

最新美股資料顯示，費城半導體指數上漲 1.30%，那斯達克百大指數卻下跌 0.12%。這組落差支持半導體相對強勢的解讀，但無法單靠指數表現確認資金流入規模，也不足以把整個科技板塊都視為同步轉強。對台灣而言，半導體權值與先進製程供應鏈可能得到情緒支撐；能否延伸到設備、封裝與其他電子業，仍要看台灣開盤後的承接廣度與訂單訊息。

今晨西德州原油期貨報價為 94.28 美元，較資料所列前值上漲 1.34%。這是盤前可見的期貨報價，並非原油結算價。它讓能源成本成為今天不能忽略的限制：運輸與高耗能製造可能先承受支出壓力，之後才看售價能否轉嫁。石化業還須比較原料與產品價差，庫存評價利益不等於持續獲利改善；電子製造則要看能源、物流與材料負擔，會不會吃掉營收成長帶來的利潤。

美國財政部最新日資料顯示，十年期公債殖利率為 4.8%。這個水準代表企業與股票評價仍須面對資金成本約束；單筆資料不能證明殖利率正在加速上升，也不能確認市場已改變降息預期。我的推論是，若能源成本持續增加，企業獲利與寬鬆期待可能同時受到檢驗，高估值電子對這種組合尤其敏感。

## 台股需要的是擴散確認

目前價格已反映半導體相對強勢，卻無法由漲幅推算市場究竟提前反映多少成長。接下來可能重新定價的，是訂單能否轉成毛利與現金流，以及能源壓力是否令利率維持在較高水準。金融業也不能把長端利率偏高一概當成利多，利差機會仍須與債券評價及信用風險一起衡量。

若油價回落、長端利率壓力緩和，且台灣非電子類股也加入漲勢，目前偏分化的判斷就應轉得更正面；若油價續升、企業出現成本轉嫁困難，並伴隨半導體承接轉弱，則需要下修對大盤韌性的看法。今天先用漲勢廣度與成本變化檢驗這個判斷。美股指數、原油期貨與公債日資料的時間口徑不同，適合用來辨認壓力來源，不宜當作同一瞬間的因果證明。'''

def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now)
    assert now.date().isoformat() == DAY and 'pre_tw_open' in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings('.env'))
    c = store._cursor()
    c.execute("SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='pre_tw_open'", (DAY,))
    assert c.fetchone() is None, 'Existing row requires review; preserve delivery state.'
    c.execute('SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (%s,%s,%s,%s)', tuple(IDS))
    events = [dict(zip(['id','event_id','source','title','summary','published_at'], row)) for row in c.fetchall()]
    assert len(events) == 4
    assert all(str(e['published_at'])[:10] == '2026-09-08' for e in events)
    structured = dict(schema_version='codex-market-analysis-v1', headline='半導體韌性遇上能源與利率約束', sentiment='neutral', confidence='medium', thesis='台股中性偏分化，電子支撐仍須接受成本與承接廣度檢驗。', evidence=[dict(event_id=i) for i in IDS], tw_sector_transmission=['半導體與先進製程情緒支撐','運輸與製造成本壓力','金融利差與債券評價拉鋸'], invalidation=['油價與利率壓力緩和且漲勢擴散','成本續升與半導體承接轉弱'], evidence_limitations=['期貨、指數及公債日資料時間口徑不同','未由單筆殖利率推斷變動方向'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = style_check(SUMMARY)
    assert verifier['ok'] and style['ok'], json.dumps(dict(verifier=verifier, style=style))
    raw = dict(automation_id='market-analysis-codex-guard-pre-open', generator='codex_automation', display_title=DAY, calendar=calendar.to_dict(), evidence_event_ids=IDS, claim_verifier=verifier, trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'), style_checks=style, external_provider_api_called=False)
    print(json.dumps(dict(dry_run=True, claim_verifier=verifier, style_checks=style, characters=len(SUMMARY))))
    if '--apply' not in sys.argv:
        return
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(analysis_date=DAY, analysis_slot='pre_tw_open', scheduled_time_local='07:30', model='codex-local-judgment', prompt_version='codex-flexible-briefing-memo-v1', summary_text=SUMMARY, events_used=4, market_rows_used=0, push_enabled=True, pushed=False, raw_json=json.dumps(raw,ensure_ascii=False), structured_json=json.dumps(structured,ensure_ascii=False)))
    c.execute('SELECT summary_text,raw_json,structured_json,push_enabled,pushed FROM t_market_analyses WHERE id=%s',(row_id,))
    row = c.fetchone()
    c.execute('SELECT COUNT(*) FROM t_trade_signals WHERE analysis_id=%s',(row_id,))
    signals = c.fetchone()[0]
    assert row[0] == SUMMARY and json.loads(row[1]) == raw and json.loads(row[2]) == structured
    assert row[3] == 1 and row[4] == 0 and signals == 0 and style_check(row[0])['ok']
    print(json.dumps(dict(analysis_id=row_id, claim_verifier_ok=verifier['ok'], trust_gate=raw['trust_gate'], push_enabled=row[3], pushed=row[4], structured_json_present=True, style_checks=style_check(row[0]), external_provider_api_called=False, trade_signal_count=signals)))
    c.close()

if __name__ == '__main__':
    main()
