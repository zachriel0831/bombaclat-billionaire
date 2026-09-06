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

DATE = '2026-09-07'
IDS = [865075, 862699, 849343, 866307]
SUMMARY = '''市場目前的拉鋸，是 AI 建設的實體需求能否抵住能源與資金成本。我的盤前判斷是台股中性偏正面，支撐較集中在伺服器、電源與半導體供應鏈；最大不確定性是成本上升會不會先侵蝕獲利，再壓縮市場願意給的評價。週末沒有新的美股現貨收盤，今天需要靠台股開盤後的類股廣度確認承接，不能直接把前一交易日的強勢外推。

## 訂單有支撐，成本也在追上

經濟日報今晨報導，亞馬遜雲端服務擴大 AI 伺服器機櫃拉貨，相關零組件供應商擴產因應。這提供了比單純資本支出宣示更接近出貨端的線索：算力建設可沿著機櫃、電源與散熱傳到台灣。但拉貨消息仍不等於整條產業鏈的利潤同步改善，擴產進度、交付與收款才決定需求如何變成現金流。

同一股需求也有另一面。經濟日報轉述金融時報分析，AI 帶動記憶體供應吃緊，晶片漲價可能延續到消費電子售價。據此推估，台灣記憶體供應端可能得到價格支撐，電腦與其他終端組裝業者卻面臨成本轉嫁考驗。若售價上調削弱消費需求，科技業內部就會出現分化，不能用 AI 需求強來概括所有電子產業。

融資環境目前沒有提供全面退潮的證據。上週公布的美國高收益債利差為 2.65%，前值為 2.66%，至少這筆觀察未顯示信用風險溢酬擴大。它讓需求與獲利仍有機會主導評價，但屬落後觀察，不能保證今天資金持續流入台股，也不能據此推論長天期公債殖利率已下降。

今晨西德州原油報價約 91.48 美元。這個成本水位讓能源仍是台灣出口製造、運輸與耗能產業的重要變數；若油價再上行，除了壓迫利潤，也可能透過通膨預期提高長端利率，抵銷科技需求帶來的評價支撐。

我的解讀是，AI 需求延續已是市場熟悉的敘事，仍待重新定價的是企業能留下多少獲利，以及能源成本會不會反向加速。若後續交付與獲利改善、電子漲勢擴散，且油價及信用利差沒有轉強，中性偏正面的判斷會更有依據；若訂單延後、消費端無法承受漲價，或油價與信用利差同步走高，就應下修這個判斷。今天先把價格承接與獲利傳導分開觀察，避免把產業需求的長線故事當成短線全面上漲的保證。'''

def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now)
    assert now.date().isoformat() == DATE and 'pre_tw_open' in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings('.env'))
    c = store._cursor()
    c.execute('SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (%s,%s,%s,%s) ORDER BY id', tuple(IDS))
    events = [dict(zip(['id','event_id','source','title','summary','published_at'], row)) for row in c.fetchall()]
    assert len(events) == len(IDS)
    structured = {'schema_version':'codex-market-analysis-v1', 'headline':'AI 拉貨支撐台股，成本與獲利決定擴散程度', 'sentiment':'cautiously_constructive', 'confidence':'medium', 'evidence':[{'event_id':i} for i in IDS], 'thesis':'AI 實體需求支持台股中性偏正面，成本上升限制評價。', 'tw_sector_transmission':['伺服器、電源、散熱的交付需求','記憶體供應與終端組裝成本分化','能源成本傳到運輸與耗能製造'], 'invalidation':['訂單延後或利潤轉弱','油價與信用利差同步上升'], 'evidence_limitations':['信用利差觀察日期為 2026-09-03','週末無新的美股現貨收盤']}
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
