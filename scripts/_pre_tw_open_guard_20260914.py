"""Reviewed local memo; dry-run unless --apply is supplied."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260909 import (
    MarketAnalysisRecord, MySqlEventStore, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-09-14'
IDS = [921593, 921472, 921469]
SUMMARY = '''市場今晨重新衡量的是 AI 成長預期與通膨壓力能否並存。我的台股盤前判斷偏審慎：電子供應鏈仍有長期需求敘事，但能源上漲與政策預期變化，可能先壓縮市場願意給的估值。最大不確定性是這次期貨轉弱只是週末消息後的短暫調整，還是企業投資與獲利預期也將跟著下修。

週五的支撐，遇上週一的新壓力

經濟日報今晨報導，美股主要指數期貨開盤下跌、油價上揚，市場同時消化 AI 發展速度疑慮與高於預期的美國通膨消息。這說明盤前焦點正落在成長與資金成本的拉鋸；報導提到的升息押注仍屬市場預期，不能當成政策已決定，也不能直接推論企業已全面削減投資。對台灣先進製程、封裝、伺服器與散熱供應鏈，應分別確認客戶支出計畫、實際交付及獲利，避免把情緒變化直接當成訂單衰退。

價格端已有成本訊號。今晨西德州原油期貨報價為每桶 102.35 美元，上漲 2.30%。這是盤中報價，並非結算價。據此推估，若漲勢延續，台灣航空、運輸及高耗能製造的成本轉嫁壓力會增加，電子業也可能透過物流與材料受到影響；石化則需看產品價格能否跟上原料，不能單憑油價上漲判斷獲利。能源若進一步推高通膨預期，還可能讓長端利率更難回落，使科技股同時面對成本與折現率的約束。

另一個必須保留的背景，是上週五費城半導體指數上漲 1.81%。這代表前一交易日半導體仍有承接，卻不是週一盤前的即時風險訊號。週末沒有新的美股現貨收盤，今天期貨走弱與週五現貨走強可以同時成立；兩者的時間差，正是台股開盤需要重新消化的部分。若電子權值穩住，但其他供應鏈持續轉弱，指數表現也未必代表整體風險偏好改善。

接下來會改變判斷的證據

期貨已反映部分疑慮，但目前無法量化市場已消化多少通膨與 AI 投資風險。後續重新定價的重點，是政策訊息是否比預期更緊，以及企業能否維持交付與利潤。若油價回落、政策壓力緩和，且台灣電子承接擴散、客戶投資計畫維持，這份偏審慎的判斷就應轉得更正面；若油價高檔延續，又出現投資延後或毛利下修，壓力就可能從估值進一步傳到獲利。今天先看這些訊號是否相互印證，不宜把單一盤前波動外推成整週方向。'''


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now)
    assert str(now.date()) == DAY and 'pre_tw_open' in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings('.env'))
    c = store._cursor()
    c.execute("SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='pre_tw_open'", (DAY,))
    assert c.fetchone() is None, 'Existing row needs inspection; preserve delivery state.'
    c.execute('SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (%s,%s,%s)', tuple(IDS))
    events = [dict(zip(['id','event_id','source','title','summary','published_at'], row)) for row in c.fetchall()]
    by_id = {e['id']: e for e in events}
    assert len(events) == 3
    assert '2026-09-14T07:27' in str(by_id[921593]['published_at'])
    assert 'value=102.35;' in by_id[921472]['summary'] and 'change_percent=+2.30%' in by_id[921472]['summary']
    assert 'as_of=2026-09-13T23:10:00+00:00' in by_id[921472]['summary']
    assert 'change_percent=+1.81%' in by_id[921469]['summary'] and 'as_of=2026-09-11' in by_id[921469]['summary']
    structured = dict(schema_version='codex-market-analysis-v1', confidence='medium', sentiment='cautious',
        headline='週一能源與政策壓力考驗半導體承接', thesis='台股偏審慎，關鍵是估值壓力是否傳到企業投資與獲利。',
        evidence=[dict(event_id=i) for i in IDS],
        tw_sector_transmission=['先進製程、封裝與伺服器估值及訂單','航空、運輸與高耗能製造成本','石化產品與原料價差'],
        invalidation=['油價及政策壓力緩和，電子承接擴散且客戶投資維持','油價高檔延續，投資延後或毛利下修'],
        evidence_limitations=['週五半導體現貨僅供前次交易背景','期貨為週一盤前報價，政策押注非決策','彙總油價與原始報價不一致，採較新原始報價'])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = style_check(SUMMARY)
    assert verifier['ok'] and style['ok'], json.dumps(dict(verifier=verifier, style=style))
    raw = dict(automation_id='market-analysis-codex-guard-pre-open', generator='codex_automation', display_title=DAY,
        calendar=calendar.to_dict(), evidence_event_ids=IDS, claim_verifier=verifier,
        trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'),
        style_checks=style, external_provider_api_called=False)
    print(json.dumps(dict(dry_run='--apply' not in sys.argv, claim_verifier=verifier, style_checks=style, characters=len(SUMMARY))))
    if '--apply' not in sys.argv:
        return
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(analysis_date=DAY, analysis_slot='pre_tw_open',
        scheduled_time_local='07:30', model='codex-local-judgment', prompt_version='codex-flexible-briefing-memo-v1',
        summary_text=SUMMARY, events_used=3, market_rows_used=0, push_enabled=True, pushed=False,
        raw_json=json.dumps(raw,ensure_ascii=False), structured_json=json.dumps(structured,ensure_ascii=False)))
    c.execute('SELECT summary_text,raw_json,structured_json,push_enabled,pushed FROM t_market_analyses WHERE id=%s', (row_id,))
    row = c.fetchone()
    c.execute('SELECT COUNT(*) FROM t_trade_signals WHERE analysis_id=%s', (row_id,))
    signals = c.fetchone()[0]
    assert row[0] == SUMMARY and json.loads(row[1]) == raw and json.loads(row[2]) == structured
    assert row[3] == 1 and row[4] == 0 and signals == 0 and style_check(row[0])['ok']
    print(json.dumps(dict(analysis_id=row_id, claim_verifier_ok=verifier['ok'], trust_gate=raw['trust_gate'],
        push_enabled=row[3], pushed=row[4], structured_json_present=True, style_checks=style_check(row[0]),
        external_provider_api_called=False, trade_signal_count=signals)))


if __name__ == '__main__':
    main()
