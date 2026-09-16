"""Local pre-open memo; dry-run by default, --apply stores the missing row."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260909 import (
    MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-09-16'
IDS = [937627, 937626, 937632, 937630]
SUMMARY = '''市場在盤前呈現的是電子股內部的分歧：半導體指數略有支撐，卻沒有帶動大型科技股同步轉強。我的台股判斷是中性偏審慎，電子供應鏈有承接機會，但還不足以推論整體風險偏好回升；最大不確定性，是半導體的相對韌性會擴散，還是少數成分股的表現掩蓋了其他環節的壓力。

半導體有支撐，台灣權值未必同步

前一個美股交易日，費城半導體指數上漲 0.40%，那斯達克百大指數下跌 0.65%。這組對照說明電子產業內部存在選擇性承接，卻不能單憑價格判斷資金正在全面轉向半導體，更不能把反彈當成新增訂單。對台灣先進製程、封裝、伺服器與散熱供應鏈，較合理的推論是海外評價提供部分支撐，後續仍須由客戶支出、交付與毛利展望確認。

台積電美國存託憑證同日下跌 1.02%，正好提醒我們不能直接把半導體指數的漲幅套到台股權值。不同成分股的權重、交易時段與資金部位都可能造成差異，目前不能確定是哪個因素主導。若台灣大型電子股無法跟上產業指數的韌性，指數層面的支撐就可能有限；反過來，若承接從權值擴散到相關供應鏈，才較有理由提高對整體電子盤勢的信心。這是後續確認條件，並非今日台股已出現的走勢。

油價小跌，成本壓力仍不能略過

今晨盤前西德州原油期貨報每桶 105.39 美元，下跌 0.42%，屬盤中報價而非結算價。方向上略有緩和，但一次回落還不足以證明能源成本壓力消失。若油價維持在這個水準，航空、運輸與高耗能製造仍需面對成本轉嫁問題；電子業也可能經由物流與材料受到影響。石化則要看產品報價與原料成本的差距，不能把原油漲跌直接換算成獲利方向。能源若妨礙通膨降溫，也可能限制資金成本下降的空間，但這仍是情境推演，不代表利率已確認轉向。

接下來的重新定價，取決於分歧能否收斂

目前價格已顯示市場對不同電子環節給出不同評價，尚無法量化其中反映了多少需求或獲利疑慮。若大型科技與台灣權值回穩、半導體承接擴散，並有企業展望維持及能源成本回落配合，中性偏審慎的判斷就應往正面調整；若半導體支撐消退、企業展望轉弱，或油價再度上行，壓力便可能同時落在估值與利潤。本文依盤前資訊判讀，未納入台股今日開盤後走勢，也不把單晚價差當成整週趨勢。'''


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
    cutoff = datetime.fromisoformat(DAY+'T07:30:00+08:00')
    for i, token in zip(IDS, ['change_percent=+0.40%', 'change_percent=-0.65%', 'change_percent=-1.02%', 'value=105.39;']):
        assert token in by_id[i]['summary']
        published = datetime.fromisoformat(str(by_id[i]['published_at']))
        assert cutoff-timedelta(hours=24) <= published <= cutoff
    assert 'change_percent=-0.42%' in by_id[937630]['summary']
    structured = dict(schema_version='codex-market-analysis-v1', confidence='medium', sentiment='cautious',
        headline='電子走勢分歧，能源成本仍待觀察', thesis='台股中性偏審慎，半導體韌性能否擴散仍待確認。',
        evidence=[dict(event_id=i) for i in IDS],
        tw_sector_transmission=['電子權值與半導體供應鏈評價','航空、運輸及高耗能製造成本','石化產品與原料價差'],
        invalidation=['科技與台灣權值回穩、半導體承接擴散且企業展望維持','半導體支撐消退、展望轉弱或能源成本上升'],
        evidence_limitations=['截至盤前，未納入台股開盤後資訊','原油為盤中期貨報價','以原始報價取代不一致的彙總油價'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = style_check(SUMMARY)
    assert verifier['ok'] and style['ok'], json.dumps(dict(verifier=verifier, style=style))
    raw = dict(automation_id='market-analysis-codex-guard-pre-open', generator='codex_automation', display_title=DAY,
        calendar=calendar.to_dict(), evidence_event_ids=IDS, claim_verifier=verifier,
        trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'),
        style_checks=style, external_provider_api_called=False, generated_at=now.isoformat(),
        late_generation=now > cutoff, evidence_cutoff_local=cutoff.isoformat())
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
