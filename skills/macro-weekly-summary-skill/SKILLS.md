---
name: weekly-macro-line-brief
description: Build market-analysis and weekly-summary prompts for Taiwan investors from recent event facts, market context, RAG analogues, and fixed-watchlist rules. Use when changing macro weekly summary, daily market analysis prompt assets, LINE brief shape, section contracts, or prompt safety rules in data-collecting.
---

# Weekly Macro Summary Skill

This file is intentionally named `SKILLS.md` for compatibility with existing prompt-loading code. Keep it in sync with `SKILL.md` when editing this skill.

## Purpose

Guide generated weekly summaries and market-analysis drafts so they are evidence-grounded, readable in LINE, and useful for Taiwan investors.

## Inputs

- Recent local relay event source facts.
- Stored market-context facts and deterministic market signal rows.
- Recent market index snapshots when available.
- Hybrid RAG historical analogues from embeddings.
- Fixed ten-stock watchlist context for machine-readable downstream signal rows when explicitly needed; daily visible reports no longer render the fixed-watchlist section.

## Output Principles

- Explain evidence -> transmission mechanism -> Taiwan market implication.
- Use short paragraphs and compact bullets.
- If evidence is stale or thin, lower confidence and describe observation limits in reader-facing language.
- Use a professional-but-conversational Taiwan macro commentary tone: first say what the market is trading, then explain which data supports or breaks that chain.
- Keep useful terms such as regime, liquidity, Fed path, credit spread, VIX, SOX, and DXY, but explain why each matters to Taiwan investors.
- Do not turn the report into a beginner lazy bag; keep the mechanism, but translate it into market implications.
- Keep historical RAG examples as analogues only; never present them as current evidence.
- Do not include internal event IDs, source row IDs, citation-only numeric lists, internal pipeline labels, table names, API/guard implementation notes, provider names, quota notes, or custom numeric handles in visible reports.
- Do not show internal source labels, table names, snake_case fields, scheduled task names, provider names, guard names, or custom score labels; translate them into reader-facing Traditional Chinese market implications.
- Do not invent arbitrary Taiwan ticker recommendations outside the fixed watch pool.
- Daily visible reports must focus on macro and industry/sector interpretation. Mention individual companies only as mega-cap transmission examples such as NVIDIA, TSMC, or Magnificent Seven / 美股七巨頭.
- Pushed daily reports should usually land around 800-1400 Chinese characters; shorter close digests are acceptable only when the window is thin and all required sections still exist.
- Do not output order intents, broker actions, or automated trading instructions.

## Daily Market Analysis Sections

Use this readable author-style macro flow unless the calling code supplies a stricter section contract:

1. 今日主命題
2. 三個證據
3. 市場正在定價什麼
4. 台股傳導
5. 反證條件
6. 風險與觀察限制

`三個證據` should contain exactly three bullets. Each bullet should connect source fact -> mechanism -> why it matters now. `市場正在定價什麼` should name what is already reflected in prices and what can still be repriced.

For daily `market_analysis`, do not append `今日個股觀察` and do not write `台股配置` as a visible section. If the structured JSON contains `stock_watch`, treat it as machine-readable downstream signal context only. The visible report may mention companies such as NVIDIA, TSMC, or Magnificent Seven / 美股七巨頭 only to explain macro/sector transmission, not as a watchlist, entry plan, stop-loss, or target-price list.

## Weekly Summary Sections

Weekly reports use:

1. 週總經
2. 下週台股配置
3. 下週觀察清單

Weekly reports are allocation/watchlist briefs. They should not produce intraday entry, take-profit, stop-loss, or order-level instructions.

## Fixed Watch Pool

Only these Taiwan tickers may appear in machine-readable fixed-watchlist signal context unless the user changes the governing spec. Do not render this pool as a daily visible `今日個股觀察` section.

| Ticker | Name | Notes |
|---|---|---|
| `2330` | TSMC | AI demand and semiconductor cycle. |
| `2317` | Hon Hai | AI server and assembly supply-chain proxy. |
| `2454` | MediaTek | IC design, handset cycle, edge AI / ASIC proxy. |
| `2308` | Delta Electronics | Power supply and AI data-center infrastructure proxy. |
| `2881` | Fubon Financial | Rates, insurance, and financial conditions proxy. |
| `2882` | Cathay Financial | Rates and insurance/financial conditions. |
| `2485` | Zinwell | Networking and communications watch item. |
| `3535` | Favite | Equipment / optoelectronics watch item. |
| `3715` | Dynamic Holding | PCB and auto electronics proxy. |
| `2351` | SDI | Lead frame and semiconductor materials proxy. |

## Related Docs

- [../../memory-bank/rag-operations.md](../../memory-bank/rag-operations.md)
- [../../spec/market-analysis-fixed-watchlist-functional-spec.md](../../spec/market-analysis-fixed-watchlist-functional-spec.md)
- [../../spec/market-analysis-fixed-watchlist-data-contract.md](../../spec/market-analysis-fixed-watchlist-data-contract.md)
- [../line-brief-format-skill/line-weekly-brief.md](../line-brief-format-skill/line-weekly-brief.md)
- [../line-brief-format-skill/rubric.md](../line-brief-format-skill/rubric.md)
