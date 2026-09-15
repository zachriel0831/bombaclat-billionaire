"""Local pre-open evidence memo; dry-run by default, --apply stores it."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _pre_tw_open_guard_20260914 import (
    MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-09-15'
IDS = [928570, 928569, 928590, 928573]
SUMMARY = '''市場在這個盤前窗口呈現的，是半導體承受比大型科技股更重的重新定價壓力。我的台股判斷偏審慎：電子權值與 AI 供應鏈可能先面對估值壓縮，能源成本又限制企業利潤的緩衝。最大不確定性是這次賣壓主要來自持倉調整，還是開始反映客戶支出與獲利預期轉弱；單靠一晚價格，還不能把後者當成定論。

半導體先跌，利率沒有提供明顯緩衝

前一個美股交易日，費城半導體指數下跌 5.86%，那斯達克百大指數下跌 0.82%。兩者同向，但跌幅差距說明壓力在半導體更集中，不能只用科技股普遍回檔概括。據此推估，台灣先進製程、封裝與伺服器供應鏈會先受到海外評價調整牽動；不過，股價下跌本身不是訂單取消的證據，需求是否受損仍須由客戶投資計畫、交付及毛利展望確認。

利率是另一層約束。美國財政部前一交易日的十年期公債殖利率為 4.97%。這個水準意味長期資金成本仍是評價科技成長的門檻，但單一日值不能證明利率突然跳升，更不能解釋全部半導體跌幅。對台灣電子業而言，若資金成本維持而獲利預期沒有同步改善，市場可能降低願意支付的估值；即使訂單維持成長，股價也未必能照原先敘事延伸。

能源則把壓力從評價帶向成本。今晨盤前西德州原油期貨報價為每桶 101.96 美元，上漲 0.56%，屬盤中報價而非結算價。若能源成本維持偏高，航空、運輸及高耗能製造的成本轉嫁能力就更重要，電子供應鏈也可能經由材料與物流受到影響。石化要看產品報價能否跟上原料，不能把油價上漲直接等同獲利改善。油價是否繼續影響通膨與政策預期，仍是後續風險，尚不能寫成已發生的政策轉向。

什麼會讓這份審慎判斷改變

價格已反映部分半導體疑慮，但目前無法量化市場消化了多少獲利風險。接下來能帶動重新定價的，是企業展望是否維持，以及利率與能源能否同時減輕壓力。若半導體相對弱勢收斂、客戶投資維持，且長端利率與油價回落，台股電子的審慎判斷就應轉得更正面；若相對弱勢延續，又出現投資延後或利潤下修，壓力便可能從估值傳到盈餘。本文依盤前資訊判讀，未納入台股今日開盤後走勢，不能據此認定當日盤面已驗證上述情境。'''


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and 'pre_tw_open' in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings('.env'))
    c = store._cursor()
    c.execute("SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='pre_tw_open'", (DAY,))
    assert c.fetchone() is None, 'Existing row requires inspection; preserve delivery state.'
    c.execute('SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (%s,%s,%s,%s)', tuple(IDS))
    events = [dict(zip(['id','event_id','source','title','summary','published_at'], r)) for r in c.fetchall()]
    by_id = {e['id']: e for e in events}
    for i, token in zip(IDS, ['change_percent=-5.86%', 'change_percent=-0.82%', 'value=4.97;', 'value=101.96;']):
        assert token in by_id[i]['summary'] and '2026-09-14' in str(by_id[i]['published_at'])
    assert 'change_percent=+0.56%' in by_id[928573]['summary']
    structured = dict(schema_version='codex-market-analysis-v1', confidence='medium', sentiment='cautious',
        headline='半導體重估，利率與能源限制緩衝', thesis='台股電子偏審慎，需區分估值調整與盈餘下修。',
        evidence=[dict(event_id=i) for i in IDS],
        tw_sector_transmission=['先進製程、封裝及伺服器評價','航空、運輸與高耗能製造成本','石化產品與原料價差'],
        invalidation=['半導體相對弱勢收斂、客戶投資維持且利率油價回落','投資延後或利潤下修使壓力傳到盈餘'],
        evidence_limitations=['截至盤前，未納入台股開盤後資訊','原油為盤中期貨報價','價格不能直接證明訂單變化'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = style_check(SUMMARY)
    assert verifier['ok'] and style['ok'], json.dumps(dict(verifier=verifier, style=style))
    raw = dict(automation_id='market-analysis-codex-guard-pre-open', generator='codex_automation', display_title=DAY,
        calendar=calendar.to_dict(), evidence_event_ids=IDS, claim_verifier=verifier,
        trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'),
        style_checks=style, external_provider_api_called=False, generated_at=now.isoformat(),
        late_generation=True, evidence_cutoff_local=DAY+'T07:30:00+08:00')
    print(json.dumps(dict(dry_run='--apply' not in sys.argv, claim_verifier=verifier, style_checks=style, characters=len(SUMMARY))))
    if '--apply' not in sys.argv:
        return
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(analysis_date=DAY, analysis_slot='pre_tw_open',
        scheduled_time_local='07:30', model='codex-local-judgment', prompt_version='codex-flexible-briefing-memo-v1',
        summary_text=SUMMARY, events_used=4, market_rows_used=0, push_enabled=True, pushed=False,
        raw_json=json.dumps(raw,ensure_ascii=False), structured_json=json.dumps(structured,ensure_ascii=False)))
    print(json.dumps(dict(analysis_id=row_id)))


if __name__ == '__main__':
    main()
