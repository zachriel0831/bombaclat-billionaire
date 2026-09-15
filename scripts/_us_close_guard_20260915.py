"""Local-only close memo; dry-run unless --write is supplied."""
import json
import sys
from datetime import datetime, timedelta, timezone
from _us_close_guard_20260909 import (
    MySqlEventStore, MarketAnalysisRecord, load_settings, style_check,
    verify_claim_coverage, resolve_market_calendar_state, allowed_analysis_slots,
)

DAY = '2026-09-15'
IDS = [928166, 928052, 926608, 927815]
SUMMARY = """這次美股收盤讓台灣投資人面對的壓力更集中：半導體的成長預期受到質疑，利率與能源成本又同時拉高估值門檻。我的判斷是，台股大型電子與 AI 供應鏈短線承接的外部環境轉弱，但目前證據仍不足以判定訂單已經反轉；最需要分清楚的，是市場先調低願意付出的價格，還是企業真的開始縮減投資。

美股收盤報導顯示，費城半導體指數下跌 5.86%，台積電美國存託憑證下跌 3.52%。同一時段的消息指出，部分 AI 公司高層因安全疑慮呼籲放緩技術發展，市場因而擔心資本支出降溫。這把壓力直接帶到台灣先進製程、先進封裝與伺服器供應鏈：只要投資時程被往後想像，遠期獲利的估值就可能先受壓。不過，呼籲放慢技術發展不等於已宣布刪減設備預算，股價下跌也不能當成訂單取消的證明。

資金成本讓這次修正更難只用科技消息解釋。中央社報導，美國十年期公債殖利率在盤中升破 5%，並將變化連到中東戰事與油價引發的通膨疑慮。這是盤中水準，不是收盤利率；它的意義在於，成長預期受壓時，折現遠期獲利所用的利率也沒有提供緩衝。對資本密集的半導體與資料中心建設而言，較高融資成本可能使投資人更重視現金流與投資回收時間，而不是只看需求故事。

能源端的壓力則有具體供應背景。收盤後的原油報導指出，沙烏地關閉重要輸油管道，引發供應吃緊疑慮，西德州原油期貨結算升至每桶 101.39 美元。對台灣而言，油價上升可能推高運輸、石化原料與製造成本，也可能減少消費者其他支出的空間。石化業仍須分辨原料漲價與產品售價能否同步調整，不能直接把高油價視為整個產業的利多。能源壓力若持續，電子需求即使有韌性，也未必足以抵銷整體估值承受的利率壓力。

價格已反映部分半導體成長疑慮，但無法由單晚跌幅判斷是否消化充分。接下來仍可能重新定價的，是企業實際資本支出計畫、能源供應恢復速度，以及高利率維持多久。若企業維持投資進度、油價與殖利率回落，且半導體相對大盤的弱勢收斂，這份偏保留的判斷就需要調整；若投資縮減獲得正式確認，或能源與利率壓力延續，則估值修正可能進一步傳到獲利預期。本次判斷以美股收盤及相關報導為準，尚不能據此認定台灣當日資金流向已經改變。"""


def main():
    calendar = resolve_market_calendar_state(datetime.now(timezone(timedelta(hours=8))))
    assert str(calendar.local_date) == DAY and 'us_close' in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings('.env'))
    c = store._cursor()
    def rows(sql, params=()):
        c.execute(sql, params)
        return json.loads(json.dumps([dict(zip([d[0] for d in c.description], r)) for r in c.fetchall()], default=str))
    assert not rows("SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='us_close'", (DAY,))
    events = rows('SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (928166,928052,926608,927815)')
    assert len(events) == 4 and all(e['published_at'].startswith(DAY) for e in events)
    structured = dict(schema_version='codex-market-analysis-v1', confidence='medium',
        thesis='半導體成長預期與利率、能源壓力同時壓縮台灣電子估值空間。',
        evidence_event_ids=IDS,
        tw_sector_transmission=['先進製程、封裝與伺服器估值承壓', '運輸與製造成本上升', '石化利潤取決於成本轉嫁'],
        invalidation=['企業維持投資且油價與利率回落、半導體相對弱勢收斂'],
        caveat='技術放緩呼籲不等於資本支出削減；殖利率為盤中值。')
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=[])
    style = style_check(SUMMARY)
    assert verifier['ok'] and style['ok'], json.dumps(dict(verifier=verifier, style=style))
    raw = dict(automation_id='market-analysis-codex-guard-us-close', generator='codex_automation', display_title=DAY,
        calendar=calendar.to_dict(), evidence_event_ids=IDS, claim_verifier=verifier,
        trust_gate=dict(version='market-analysis-trust-gate-v1', ok=True, reason='claim_verifier_ok'),
        style_checks=style, external_provider_api_called=False)
    push = not calendar.tw.is_trading_day
    print(json.dumps(dict(dry_run=True, verifier=verifier, style=style, push_enabled=push)))
    if '--write' not in sys.argv:
        return
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(analysis_date=DAY, analysis_slot='us_close',
        scheduled_time_local='05:00', model='codex-local-judgment', prompt_version='codex-flexible-briefing-memo-v1',
        summary_text=SUMMARY, events_used=4, market_rows_used=0, push_enabled=push, pushed=False,
        raw_json=json.dumps(raw, ensure_ascii=False), structured_json=json.dumps(structured, ensure_ascii=False)))
    row = rows('SELECT summary_text,raw_json,structured_json,push_enabled,pushed FROM t_market_analyses WHERE id=%s', (row_id,))[0]
    count = rows('SELECT COUNT(*) n FROM t_trade_signals WHERE analysis_id=%s', (row_id,))[0]['n']
    assert row['summary_text'] == SUMMARY and json.loads(row['raw_json']) == raw
    assert json.loads(row['structured_json']) == structured and bool(row['push_enabled']) == push
    assert not row['pushed'] and count == 0 and style_check(row['summary_text'])['ok']
    print(json.dumps(dict(analysis_id=row_id, claim_verifier_ok=verifier['ok'], trust_gate=raw['trust_gate'],
        push_enabled=push, pushed=False, structured_json_present=True, style_checks=style,
        external_provider_api_called=False, trade_signal_count=count)))


if __name__ == '__main__':
    main()
