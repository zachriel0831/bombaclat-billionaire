"""Local weekly prose; dry-run by default, --write inserts only a missing row."""
import json
import sys
from datetime import date, datetime, timedelta, timezone
from _weekly_guard_20260913 import check, HEADINGS
from _us_close_guard_20260909 import MySqlEventStore, MarketAnalysisRecord, load_settings, verify_claim_coverage

DAY = '2026-09-20'
IDS = [954902, 954903, 954899, 963301, 963304, 963179, 963332, 954911, 954910, 963327, 967426, 967283, 956724, 955528, 966637]
SUMMARY = """週總經
本週的主線，是政策利率轉緊，風險情緒卻在後半週修復。下週台股配置可以保留成長產業的比重，但應以獲利兌現與現金流作為篩選標準，還不宜全面提高對估值的容忍度。市場已用反彈表達對升息衝擊的消化；真正尚待驗證的是，能源供應風險能否下降，讓利率與企業成本不再同時擠壓獲利。

美國聯邦基金利率目標上限本週升至 4%，下限為 3.75%；日本央行週五也升息至 1.25%。這使跨國資金面對的融資條件更緊，日圓融資部位亦可能重新評估成本，但目前不能據此斷言套利資金已大規模撤出。美國財政部截至週四的十年期公債殖利率為 4.94%，說明長期資金成本仍高；這是週四觀測值，不能替代週五收盤。

價格反應卻不是單向悲觀。週五費城半導體指數上漲 2.78%，同日西德州原油期貨報價下跌 1.81%。中央社報導，沙烏地暫停對歐洲部分原油銷售，但交易員仍認為有供應緩衝。這組訊號較支持「供應擔憂稍緩、成長資產重新獲得承接」的解讀，並不等於能源供應已恢復正常。反彈已反映部分情緒改善；若要再上修整體估值，還需要更持久的能源降溫與獲利證據。

信用與流動性提供了緩衝。截至週四，高收益債信用利差與前值持平；週三的銀行準備金增加、財政部帳戶餘額下降，方向上有助資金周轉，週五隔夜逆回購餘額則回升，訊號並非全面放鬆。因此，本週較像高資金成本下的產業分化，尚不足以判定為全面信用緊縮，也不能把美國資金緩衝直接當成台灣外資流入。

下週台股配置
風傳媒對週五盤勢的報導指出，台股大漲且外資明顯買超，表示台灣市場也已反映部分風險情緒修復。配置宜偏向具訂單能見度、成本轉嫁能力與財務韌性的產業，保留流動性；單日回補是否成為持續配置，仍需觀察後續股匯與法人資金是否同向。

先進製程、先進封裝、AI伺服器、電源與散熱可作為成長配置的核心研究方向，但應把需求與估值分開。海外半導體上漲有利情緒傳導，較高折現率卻仍會壓低遠期獲利的現值。評估重點是訂單轉成營收後，毛利與自由現金流能否跟上；若成長主要伴隨更大的資本支出與營運資金占用，就不能只憑題材給予更高評價。

能源敏感產業要看淨成本而非油價方向。航空、高耗能製造承受燃料壓力；石化取決於產品報價能否追上原料；航運則須扣除繞航、保險與燃料成本。中油宣布下週國內汽柴油凍漲，可緩和部分民生與運輸端壓力，但不能外推成所有企業能源成本都不變。金融業要同時衡量利差、債券評價與信用成本；日本升息可能影響全球資金配置，也不代表台灣金融股必然受益。

下週觀察清單
先看利率與成長能否相容：政策官員談話後，長債殖利率是否回落，信用利差是否保持穩定，半導體強勢能否延續到實際獲利預期。若利率再升且信用利差擴大，這份保留成長配置的判斷就須轉向防禦；若能源與利率同步緩和、台灣股匯及資金流持續改善，則可提高對成長產業的信心。

再看政策消息是否落實。經濟日報引述彭博報導，美方考慮延後宣布產能過剩相關關稅；延後不等於取消。後續美中磋商應觀察正式關稅與科技管制內容，是否改變台灣供應鏈接單、出口與海外投資成本，而非只憑會面氣氛推論訂單增加。

最後追蹤能源供應與成本轉嫁：沙國出口、航道與保險條件是否改善，企業毛利能否消化原料波動。風險仍是週末地緣消息、政策落差與資金回補反轉；現有資訊尚不足以量化供應缺口、最新原油庫存及產業毛利影響，信用與流動性觀測也有日期差距，配置判斷須隨證據調整。"""


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    target = date.fromisoformat(DAY)
    assert target.weekday() == 6 and 0 <= (target - now.date()).days <= 1
    store = MySqlEventStore(load_settings('.env'))
    c = store._cursor()
    def rows(sql, params=()):
        c.execute(sql, params)
        return json.loads(json.dumps([dict(zip([d[0] for d in c.description], r)) for r in c.fetchall()], default=str))
    existing = rows("SELECT id,pushed FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='weekly_tw_preopen'", (DAY,))
    assert not existing, 'Existing row: inspect delivery state before any repair'
    events = rows('SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (' + ','.join(map(str, IDS)) + ')')
    assert len(events) == len(IDS)
    for event in events:
        published = datetime.fromisoformat(event['published_at'])
        if published.tzinfo is None:
            published = published.replace(tzinfo=now.tzinfo)
        assert datetime(2026, 9, 14, tzinfo=now.tzinfo) <= published <= now
    context_count = sum(e['source'].startswith('market_context:') for e in events)
    structured = dict(schema_version='codex-market-analysis-v1', confidence='medium', section_contract=HEADINGS,
        thesis='政策轉緊但風險情緒修復；成長配置須以獲利與現金流支撐。', evidence_event_ids=IDS,
        invalidation=['利率再升且信用利差擴大', '能源利率緩和且台灣股匯與資金流改善'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = check(SUMMARY)
    style['fixed_section_template'] = True
    assert verifier['ok'], verifier
    by_id = {e['id']: e for e in events}
    for event_id, token in [(954902, 'value=4;'), (954903, 'value=3.75;'), (954899, '4.94'), (963301, '+2.78%'), (963304, '-1.81%'), (956724, '1.25%')]:
        assert token in by_id[event_id]['summary']
    history = rows('SELECT (SELECT COUNT(*) FROM t_event_embeddings) events, (SELECT COUNT(*) FROM t_analysis_embeddings) analyses')[0]
    raw = dict(dimension='weekly', delivery_owner='java', section_contract=HEADINGS,
        automation_id='market-analysis-codex-guard-weekly', external_provider_api_called=False,
        evidence_event_ids=IDS, context_rows_used=context_count, evidence_cutoff_local=now.isoformat(),
        claim_verifier=verifier, style_checks=style,
        trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'),
        rag=dict(available=history, examples_count=0, note='No analogue used as current evidence'),
        evidence=events, residual_risks=['Official Treasury observations end Thursday', 'Energy inventory and supply-loss gaps', 'Policy and weekend geopolitical uncertainty'])
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
