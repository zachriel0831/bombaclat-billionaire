---
name: weekly-macro-line-brief
description: Build market-analysis and weekly-summary prompts for Taiwan investors from relay events, market context, scorecard, RAG analogues, and fixed-watchlist rules. Use when changing macro weekly summary, daily market analysis prompt assets, LINE brief shape, section contracts, or prompt safety rules in data-collecting.
---

# Weekly Macro Summary Skill

This file is intentionally named `SKILLS.md` for compatibility with existing prompt-loading code. Keep it in sync with `SKILL.md` when editing this skill.

## Purpose

Guide generated weekly summaries and market-analysis drafts so they are evidence-grounded, readable in LINE, and useful for Taiwan investors.

## Inputs

- Recent `t_relay_events` source facts.
- Stored `market_context:*` events and deterministic `market_context:scorecard`.
- Recent `t_market_index_snapshots` rows when available.
- Hybrid RAG historical analogues from `t_event_embeddings` and `t_analysis_embeddings`.
- Fixed five-stock watchlist context when generating visible Taiwan stock sections.

## Output Principles

- Explain evidence -> transmission mechanism -> Taiwan market implication.
- Use short paragraphs and compact bullets.
- Label data gaps explicitly.
- Use a professional-but-conversational Taiwan macro commentary tone: first say what the market is trading, then explain which data supports or breaks that chain.
- Keep useful terms such as regime, liquidity, Fed path, credit spread, VIX, SOX, and DXY, but explain why each matters to Taiwan investors; avoid dense acronym piles.
- Do not turn the report into a beginner "lazy bag"; keep the mechanism, but translate it into market implications.
- Keep historical RAG examples as analogues only; never present them as current evidence.
- Do not invent arbitrary Taiwan ticker recommendations outside the fixed watch pool.
- Do not output order intents, broker actions, or automated trading instructions.

## Daily Market Analysis Sections

Use this readable macro flow unless the calling code supplies a stricter section contract:

1. Macro regime
2. Rates and liquidity
3. Cycle and earnings
4. Market sentiment
5. Taiwan allocation
6. Risk and data gaps
7. Taiwan fixed-watchlist observations when evidence exists

## Weekly Summary Sections

Weekly reports use:

1. Weekly macro
2. Next-week Taiwan allocation
3. Next-week watchlist

Weekly reports are allocation/watchlist briefs. They should not produce intraday entry, take-profit, stop-loss, or order-level instructions.

## Fixed Watch Pool

Only these Taiwan tickers may appear in visible fixed-watchlist sections unless the user changes the governing spec:

| Ticker | Name | Notes |
|---|---|---|
| `2330` | TSMC | AI demand and semiconductor cycle. |
| `2603` | Evergreen Marine | Freight rates, oil, geopolitics. |
| `2882` | Cathay Financial | Rates and insurance/financial conditions. |
| `1605` | Walsin Lihwa | Copper and infrastructure cycle. |
| `4956` | Epileds | Smaller TPEx semiconductor exposure. |

## Related Docs

- [../../memory-bank/rag-operations.md](../../memory-bank/rag-operations.md)
- [../../spec/market-analysis-fixed-watchlist-functional-spec.md](../../spec/market-analysis-fixed-watchlist-functional-spec.md)
- [../../spec/market-analysis-fixed-watchlist-data-contract.md](../../spec/market-analysis-fixed-watchlist-data-contract.md)
- [../line-brief-format-skill/line-weekly-brief.md](../line-brief-format-skill/line-weekly-brief.md)
- [../line-brief-format-skill/rubric.md](../line-brief-format-skill/rubric.md)
