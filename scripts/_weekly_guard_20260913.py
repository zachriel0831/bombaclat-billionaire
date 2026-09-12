"""Local weekly prose; dry-run by default, --write inserts only a missing row."""
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from _us_close_guard_20260909 import MySqlEventStore, MarketAnalysisRecord, load_settings, style_check, verify_claim_coverage

DAY = '2026-09-13'
HEADINGS = ['週總經', '下週台股配置', '下週觀察清單']
IDS = [901451, 902890, 898291, 899738, 902171, 902174, 902191, 902206, 895302, 895301, 902201]
SUMMARY = """週總經
本週留下的主線，是能源與利率同時擠壓估值，週五美股反彈則提醒我們，市場還沒有全面否定成長。下週台股配置宜保留成長產業的參與，但提高對現金流、成本轉嫁與財務韌性的要求。最大的變數，是中東供應風險會不會把短暫的能源漲價，變成更持久的通膨與資金成本壓力。

中央社引述美國勞工部資料，8 月消費者物價指數年增率維持 3.4%；美國財政部的週五資料顯示，十年期公債殖利率為 4.96%。前者說明物價壓力仍在，後者則是企業與股票估值面對的實際資金成本。市場報導已有升息預期，但預期不能當成決議；即使政策沒有進一步收緊，長期利率居高也足以限制市場願意為遠期獲利支付的價格。

週五費城半導體指數回升 1.81%，同日西德州原油期貨報價回落，反映部分避險情緒緩和。不過，經濟日報週末報導沙國東西向輸油管線遇襲關閉，替代出口路線也面臨中斷風險。週五價格尚不足以證明市場消化了週末消息；後續要看運輸恢復與供應實況，不能把單日油價回落解讀成能源問題已解決。

也有避免過度悲觀的反證：截至週四，高收益債信用利差較前值略降；本週較早的銀行準備金增加、財政部帳戶餘額下降，與資金緩衝改善的方向一致，但隔夜逆回購最新餘額回升，訊號並不全然寬鬆。我的判斷是，目前更像資金成本偏高下的風險重估，尚不足以定義為全面信用緊縮。這些資料日期不同，也不能直接推論資金正在流入台股。

下週台股配置
台灣週五股匯同步走弱，經濟日報報導三大法人明顯賣超；這發生在美國通膨公布及美股收盤之前，下一個交易日仍需重新確認外資反應。因此，配置重心宜放在獲利能見度與資金韌性，避免把海外反彈當成台灣資金已回流的證明。

先進製程、AI伺服器、電源與散熱仍是觀察成長需求的核心產業，但配置理由應建立在訂單轉為營收、毛利與現金流的能力。較高利率會壓低遠期獲利的現值，需求成長也可能被資本支出與營運資金占用抵銷；不能只憑產業題材，推論估值理應繼續擴張。若後續利率回落且資金回流，成長產業承受的壓力才有機會一起緩和。

能源敏感產業需分開判斷。航空與高耗能製造面對燃料及原料成本，石化要看產品報價能否追上投入成本；航運即使受運價支撐，也可能增加繞航、保險與燃料支出。金融業則須區分利差收益、債券評價與信用成本，不能把利率上升視為整個族群的單向利多。台幣走弱可能改善出口換匯收入，也提高美元原料成本；較穩健的配置判準，是淨匯率曝險與成本轉嫁能力，而非出口或內需的簡單二分。

下週觀察清單
先看政策與利率是否一致：聯準會對通膨、就業與能源的評估，是否改變市場對緊縮持續時間的理解；政策訊息發布後，短債與長債的反應是否同向。只有新聞語氣轉暖、長期資金成本卻不降，還不足以支持全面提高成長估值。

再看能源衝擊是否持續：輸油管線及航道恢復、油價與運輸成本能否共同緩和。若能源回落、殖利率下降，且台灣股匯與半導體同步改善，這份偏審慎的配置判斷就應轉向積極；若能源再漲、利率壓力擴散到信用利差，並伴隨台灣資金流出，則應提高防禦與流動性的權重。

最後把價格與獲利放在一起檢查：電子需求是否落實為現金流，成本敏感產業能否轉嫁漲價，金融業是否出現信用惡化。風險仍包括週末地緣消息跳變、政策與市場預期落差。現有資訊尚不足以量化能源供應損失、最新原油庫存與各產業毛利影響；信用及流動性資料也有時間落差，結論應隨後續證據調整。"""

def check(text):
    result = style_check(text)
    headings = [line for line in text.splitlines() if line and len(line) < 12]
    result.update(section_order=headings, template='weekly-three-section-v1')
    assert result['ok'] and headings == HEADINGS
    assert not re.search(r'[\ue000-\uf8ff]|進場|停利|止盈|stop.loss|target.price', text, re.I)
    assert 1000 <= len(text) <= 2000
    return result

def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    target = date.fromisoformat(DAY)
    assert target.weekday() == 6 and 0 <= (target - now.date()).days <= 1
    store = MySqlEventStore(load_settings('.env'))
    c = store._cursor()
    def rows(sql, params=()):
        c.execute(sql, params)
        return json.loads(json.dumps([dict(zip([d[0] for d in c.description], r)) for r in c.fetchall()], default=str))
    existing = rows("SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='weekly_tw_preopen'", (DAY,))
    assert not existing, 'Existing row: inspect delivery state before any repair'
    events = rows('SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (' + ','.join(map(str, IDS)) + ')')
    assert len(events) == len(IDS)
    assert all('2026-09-07' <= e['published_at'][:10] <= now.date().isoformat() for e in events)
    context_count = sum(e['source'].startswith('market_context:') for e in events)
    structured = dict(schema_version='codex-market-analysis-v1', confidence='medium', section_contract=HEADINGS,
        thesis='能源與利率擠壓估值；配置重視現金流與成本韌性。', evidence_event_ids=IDS,
        invalidation=['能源與殖利率回落且台灣股匯改善', '能源壓力擴散到信用與資金流出'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = check(SUMMARY)
    assert verifier['ok'], verifier
    # Independent binding checks: numeric tokens must belong to their claimed evidence.
    by_id = {e['id']: e for e in events}
    for event_id, token in [(901451, '3.4%'), (902191, '4.96'), (902171, '1.81%')]:
        assert token in by_id[event_id]['summary']
    history = rows('SELECT (SELECT COUNT(*) FROM t_event_embeddings) events, (SELECT COUNT(*) FROM t_analysis_embeddings) analyses')[0]
    raw = dict(dimension='weekly', delivery_owner='java', section_contract=HEADINGS,
        external_provider_api_called=False, evidence_event_ids=IDS, context_rows_used=context_count,
        evidence_cutoff_local=now.isoformat(), claim_verifier=verifier, style_checks=style,
        trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'),
        rag=dict(available=history, examples_count=0, note='No analogue used as current evidence'),
        evidence=events, residual_risks=['Different observation dates', 'Weekend geopolitical headlines', 'No verified inventory or quantified supply loss'])
    print(json.dumps(dict(dry_run=True, chars=len(SUMMARY), events_used=len(events), context_rows_used=context_count, style=style, verifier=verifier), ensure_ascii=False))
    if '--write' not in sys.argv:
        return
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(analysis_date=DAY, analysis_slot='weekly_tw_preopen',
        scheduled_time_local='05:10', model='codex-local-judgment', prompt_version='codex-weekly-three-section-v1',
        summary_text=SUMMARY, events_used=len(events), market_rows_used=0, push_enabled=True, pushed=False,
        raw_json=json.dumps(raw, ensure_ascii=False), structured_json=json.dumps(structured, ensure_ascii=False)))
    row = rows('SELECT * FROM t_market_analyses WHERE id=%s', (row_id,))[0]
    assert row['summary_text'] == SUMMARY and json.loads(row['raw_json']) == raw
    assert json.loads(row['structured_json']) == structured
    assert row['analysis_date'] == DAY and row['analysis_slot'] == 'weekly_tw_preopen'
    assert row['scheduled_time_local'] == '05:10' and row['prompt_version'] == 'codex-weekly-three-section-v1'
    assert row['push_enabled'] == 1 and row['pushed'] == 0
    assert row['events_used'] == len(events) and row['market_rows_used'] == 0
    assert rows('SELECT COUNT(*) n FROM t_trade_signals WHERE analysis_id=%s', (row_id,))[0]['n'] == 0
    print(json.dumps(dict(analysis_id=row_id, analysis_date=DAY, style=check(row['summary_text']), push_enabled=row['push_enabled'],
        pushed=row['pushed'], events_used=len(events), context_rows_used=context_count, external_provider_api_called=False), ensure_ascii=False))

if __name__ == '__main__':
    main()
