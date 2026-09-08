"""Local evidence-only memo; dry-run by default, --write stores the missing row."""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from event_relay.claim_verifier import verify_claim_coverage
from event_relay.config import load_settings
from event_relay.market_calendar import allowed_analysis_slots, resolve_market_calendar_state
from event_relay.service import MarketAnalysisRecord, MySqlEventStore

DAY = "2026-09-09"
EVENT_IDS = [876483, 877085, 873611]
MARKET_IDS = [377, 378, 379, 380]
SUMMARY = """這次美股收盤替台灣投資人增加的是能源成本與估值壓力。標普與道瓊都收在當日開盤之下，配合中東供應風險推升油價的消息，台股接下來要面對的，是企業獲利仍有支撐、但資金成本未必能順利下降的拉扯。我的判斷偏審慎：半導體與電子供應鏈的需求不能只憑單晚行情否定，卻也不宜把獲利成長直接換算成更高估值；最大的變數是油價衝擊會持續多久。

經濟日報報導，荷莫茲海峽航運風險升高，布蘭特期貨在紐約早盤一度逼近每桶100美元。這是盤中報價，不能當成原油結算價，但它指出了風險來源：如果運輸與供應受阻，能源成本可能沿著運費、原料與終端價格傳遞，讓通膨降溫變得更慢。對股票而言，壓力既可能來自企業成本，也可能來自市場延後對貨幣寬鬆的期待；目前還不能把這條可能的傳導鏈寫成殖利率已經確認上升。

另一端的支撐也不能漏看。鉅亨引述花旗指標，美國企業獲利預期連21週上調多於下調。這代表市場仍有獲利改善的敘事可依靠，但分析師預期並非已實現盈餘，也可能落後於能源成本的變化。美股當晚收盤低於開盤，至少說明這份獲利支撐沒有完全抵銷當日賣壓；僅憑收盤方向，仍無法判定跌勢究竟有多少來自油價、利率或其他消息。

台灣的傳導要同時看估值與成本。最新報導的8月CPI年增2.04%，使外部能源漲價更值得留意，但是否擴大到國內物價，還取決於匯率與能源價格調整。航空與高耗能製造面臨成本風險，石化則須區分原料上漲與產品報價能否跟上，不能把油漲一概視為利多。對先進製程、AI伺服器及電源散熱鏈，若寬鬆預期後退，較高估值可能先承壓，之後才由訂單、毛利率與現金流驗證需求韌性。

目前可確認的是盤面已有賣壓，還不能斷言市場已充分反映能源衝擊。後續若油價回落、航運風險緩和，且企業獲利預期持續改善，這份審慎判斷就需要下修；若油價高檔延續、通膨重新加速，再伴隨殖利率與美元走強，台灣電子估值和進口成本可能同時受壓。今天更有意義的確認，是利率、匯率與半導體表現能否互相呼應，而不是把美股單晚走弱直接外推成台股趨勢。"""


SUMMARY = SUMMARY.replace("每桶100美元", "每桶 100 美元").replace("連21週", "連 21 週").replace("8月CPI年增2.04%", "8 月 CPI 年增 2.04%")


def style_check(text):
    forbidden = ["今日主命題", "三個證據", "市場正在定價什麼", "今日一句話", "三個檢查點",
                 "市場押注與預期差", "國際消息到台股的傳導", "先看區間邊界", "現在只看",
                 "stock_watch", "推薦", "買進", "候選", "入場", "停損", "止損", "目標價",
                 "t_relay_events", "t_market_analyses", "claim_verifier", "market_context", "raw_json"]
    garbled = bool(re.search(r"\?{3,}|\ufffd|[銝脣蝢]", text))
    found = [term for term in forbidden if term in text]
    english = bool(re.search(r"(?m)^#{1,6}\s+[A-Za-z]", text))
    return dict(ok=not (garbled or found or english), garbled_text=garbled, forbidden_terms=found,
                english_section_headings=english, fixed_section_template=False, template="flexible-briefing-memo-v1")


def main():
    now = datetime.now(timezone(timedelta(hours=8)))
    calendar = resolve_market_calendar_state(now)
    assert now.date().isoformat() == DAY and "us_close" in allowed_analysis_slots(calendar)
    store = MySqlEventStore(load_settings(".env"))
    cur = store._cursor()

    def rows(sql, params=()):
        cur.execute(sql, params)
        names = [col[0] for col in cur.description]
        return json.loads(json.dumps([dict(zip(names, row)) for row in cur.fetchall()], default=str))

    existing = rows("SELECT id FROM t_market_analyses WHERE analysis_date=%s AND analysis_slot='us_close'", (DAY,))
    assert not existing, "Existing row requires review; never overwrite delivery state blindly"
    events = rows("SELECT id,event_id,source,title,summary,published_at FROM t_relay_events WHERE id IN (876483,877085,873611)")
    market = rows("SELECT id,trade_date,market_session,symbol,recorded_price FROM t_market_index_snapshots WHERE id IN (377,378,379,380)")
    assert len(events) == 3 and len(market) == 4
    assert all(e["published_at"][:10] in ("2026-09-08", DAY) for e in events)
    assert all(m["trade_date"] == "2026-09-08" for m in market)
    for symbol in ("DJIA", "S&P 500"):
        prices = {m["market_session"]: float(m["recorded_price"]) for m in market if m["symbol"] == symbol}
        assert prices["close"] < prices["open"]
    structured = dict(schema_version="codex-market-analysis-v1", confidence="medium",
        headline="能源風險與獲利支撐拉扯，台灣電子面對估值與成本雙重驗證",
        thesis="美股收盤低於開盤，油價供應風險可能延後寬鬆期待，獲利預期仍是緩衝。",
        evidence=[dict(event_id=i) for i in EVENT_IDS] + [dict(market_snapshot_ids=MARKET_IDS)],
        tw_sector_transmission=["電子估值取決於利率與獲利兌現", "航空與高耗能製造承受能源成本風險", "石化須區分原料與產品報價"],
        invalidation=["油價回落且航運風險緩和", "獲利預期改善並伴隨利率壓力下降"])
    verifier = verify_claim_coverage(summary_text=SUMMARY, structured_payload=structured, events_payload=events, market_payload=market)
    style = style_check(SUMMARY)
    assert verifier["ok"] and style["ok"], json.dumps(dict(verifier=verifier, style=style))
    push = not calendar.tw.is_trading_day
    raw = dict(automation_id="market-analysis-codex-guard-us-close", generator="codex_automation",
        display_title=DAY, calendar=calendar.to_dict(), evidence_event_ids=EVENT_IDS, market_snapshot_ids=MARKET_IDS,
        claim_verifier=verifier, trust_gate=dict(version="market-analysis-trust-gate-v1", ok=True, reason="claim_verifier_ok"),
        style_checks=style, external_provider_api_called=False)
    print(json.dumps(dict(dry_run=True, claim_verifier=verifier, style_checks=style, push_enabled=push)))
    if "--write" not in sys.argv:
        return
    row_id = store.upsert_market_analysis(MarketAnalysisRecord(analysis_date=DAY, analysis_slot="us_close",
        scheduled_time_local="05:00", model="codex-local-judgment", prompt_version="codex-flexible-briefing-memo-v1",
        summary_text=SUMMARY, events_used=len(events), market_rows_used=len(market), push_enabled=push, pushed=False,
        raw_json=json.dumps(raw, ensure_ascii=False), structured_json=json.dumps(structured, ensure_ascii=False)))
    row = rows("SELECT * FROM t_market_analyses WHERE id=%s", (row_id,))[0]
    stored_raw = json.loads(row["raw_json"])
    stored_structured = json.loads(row["structured_json"])
    signals = rows("SELECT COUNT(*) AS count FROM t_trade_signals WHERE analysis_id=%s", (row_id,))[0]["count"]
    assert row["summary_text"] == SUMMARY and stored_structured == structured
    assert bool(row["push_enabled"]) == push and not row["pushed"] and signals == 0
    assert stored_raw == raw and style_check(row["summary_text"])["ok"]
    print(json.dumps(dict(analysis_id=row_id, claim_verifier_ok=stored_raw["claim_verifier"]["ok"],
        trust_gate=stored_raw["trust_gate"], push_enabled=bool(row["push_enabled"]), pushed=bool(row["pushed"]),
        structured_json_present=bool(stored_structured), style_checks=style_check(row["summary_text"]),
        external_provider_api_called=stored_raw["external_provider_api_called"], trade_signal_count=signals)))
    cur.close()


if __name__ == "__main__":
    main()
