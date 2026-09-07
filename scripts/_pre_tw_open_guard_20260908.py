"""Local evidence only; default dry-run, --apply stores the reviewed brief."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from event_relay.config import load_settings
from event_relay.service import MarketAnalysisRecord, MySqlEventStore
from event_relay.claim_verifier import verify_claim_coverage
from event_relay.market_calendar import resolve_market_calendar_state, allowed_analysis_slots

DATE = '2026-09-08'
IDS = [869820, 869821, 869773, 869582]
SUMMARY = '''市場眼前交易的，是半導體強勢能否延續，以及能源與原料漲價會拿走多少企業獲利。我對台股盤前維持中性、偏向類股分化的判斷；最大不確定性是地緣風險造成的成本壓力，會不會蓋過電子業的成長預期。美國昨夜因勞動節休市，沒有新的美股現貨收盤可供確認，今天更需要看台灣市場自己的承接與漲勢廣度。

## 電子領漲，還不能推論全面轉強

證交所昨日資料顯示，半導體類指數上漲 2.92%，金融保險類指數卻下跌 0.23%。這組落差說明電子評價獲得支撐，但市場並非所有部門都同步受惠。我的解讀是，半導體強勢可以支撐台股氣氛，卻還不足以確認資金全面擴散；若金融與其他內需類股持續落後，指數表現就更依賴少數大型電子權值，波動也容易集中在同一條產業主線。

今晨西德州原油期貨報價為 92.59 美元，較資料所列前值上漲 1.21%。這是期貨報價，不能當作美股休市日的股票風險偏好訊號；它更直接的意義，是台灣運輸、石化與耗能製造的成本壓力仍在。石化業還要區分原料成本、庫存效果與產品價差，不能把油價上漲直接等同獲利改善。

經濟日報今晨報導，荷莫茲海峽航運風險推升油價，可能擴大的美國銅關稅則使金屬流向美國、倫敦庫存吃緊。這提供了價格之外的機制線索：原料漲價可能來自運輸與政策造成的供給摩擦，未必代表全球終端需求同步轉強。對台灣電源、線纜、散熱與電子製造而言，接單之外還要看材料成本能否轉嫁，以及交付是否被物流干擾。

## 下一步是獲利與風險溢酬的拉鋸

昨日半導體漲幅顯示，電子的正面預期已有部分反映；究竟反映多少，單靠類股價格仍無法估算。接下來可能重新定價的，是原料與運費上升後的利潤，以及通膨疑慮是否推高長端利率、壓縮科技評價。後者是需要驗證的傳導情境，並非已確認的利率變化。

若油價回穩、航運風險緩解，而且金融與非電子類股也加入漲勢，目前偏分化的判斷就應轉得更正面；若原料成本續升、企業傳出轉嫁困難，並伴隨半導體承接轉弱，則應下修對大盤韌性的看法。今天先用類股廣度與成本變化檢驗敘事，不把昨日電子強勢直接延伸成全面樂觀。'''

def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now)
    assert now.date().isoformat() == DATE and 'pre_tw_open' in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings('.env'))
    c = store._cursor()
    c.execute('SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (%s,%s,%s,%s) ORDER BY id', tuple(IDS))
    events = [dict(zip(['id','event_id','source','title','summary','published_at'], row)) for row in c.fetchall()]
    assert len(events) == len(IDS)
    structured = {'schema_version':'codex-market-analysis-v1', 'headline':'電子強勢遇上原料壓力，台股先看漲勢能否擴散', 'sentiment':'neutral', 'confidence':'medium', 'evidence':[{'event_id':i} for i in IDS], 'thesis':'半導體強勢與成本壓力拉鋸，台股中性且偏類股分化。', 'tw_sector_transmission':['半導體與金融表現分化','能源成本傳到運輸與耗能製造','銅與物流成本影響電源、線纜與電子製造'], 'invalidation':['成本回穩且非電子類股加入漲勢','成本續升並伴隨半導體承接轉弱'], 'evidence_limitations':['美國勞動節無新的美股現貨收盤','利率上升僅為條件情境，未作即時事實斷言']}
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    forbidden = ['今日一句話','三個檢查點','市場押注與預期差','國際消息到台股的傳導','先看區間邊界','現在只看','stock_watch','推薦','買進','候選','停損','目標價','入場','t_relay_events','claim_verifier']
    garbled = bool(re.search(r'\?{3,}|\ufffd|[銝脣蝢]', SUMMARY))
    style = {'ok':not garbled and not any(x in SUMMARY for x in forbidden) and not re.search(r'(?m)^#+\s+[A-Za-z]',SUMMARY), 'garbled_text':garbled,'template':'flexible-briefing-memo-v1','fixed_section_template':False}
    assert verifier['ok'] and style['ok'], json.dumps({'verifier':verifier,'style':style},ensure_ascii=False)
    raw = {'automation_id':'market-analysis-codex-guard-pre-open','generator':'codex_automation','display_title':DATE,'calendar':calendar.to_dict(),'evidence_event_ids':IDS,'claim_verifier':verifier,'trust_gate':{'version':'market-analysis-trust-gate-v1','ok':True,'reason':'claim_verifier_ok'},'style_checks':style,'external_provider_api_called':False}
    c.execute('SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot=%s',(DATE,'pre_tw_open'))
    assert c.fetchone() is None, 'Existing row requires inspection; do not overwrite delivery state.'
    if '--apply' not in sys.argv:
        print(json.dumps({'dry_run':True,'claim_verifier':verifier,'style':style,'characters':len(SUMMARY)},ensure_ascii=False))
        return
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(analysis_date=DATE,analysis_slot='pre_tw_open',scheduled_time_local='07:30',model='codex-local-judgment',prompt_version='codex-flexible-briefing-memo-v1',summary_text=SUMMARY,events_used=len(events),market_rows_used=0,push_enabled=True,pushed=False,raw_json=json.dumps(raw,ensure_ascii=False),structured_json=json.dumps(structured,ensure_ascii=False)))
    c.execute('SELECT id,push_enabled,pushed,summary_text,raw_json,structured_json FROM t_market_analyses WHERE id=%s',(row_id,))
    row = c.fetchone(); saved = json.loads(row[4]); body = json.loads(row[5])
    c.execute('SELECT COUNT(*) FROM t_trade_signals WHERE analysis_id=%s',(row_id,)); signals = c.fetchone()[0]
    assert row[1] == 1 and row[2] == 0 and row[3] == SUMMARY and body == structured and saved['external_provider_api_called'] is False and saved['claim_verifier']['ok'] and saved['trust_gate']['ok'] and signals == 0
    print(json.dumps({'analysis_id':row_id,'push_enabled':row[1],'pushed':row[2],'structured_json_present':bool(body),'claim_verifier':saved['claim_verifier'],'trust_gate':saved['trust_gate'],'style_checks':saved['style_checks'],'external_provider_api_called':False,'trade_signal_count':signals},ensure_ascii=False))
    c.close()

if __name__ == '__main__':
    main()
