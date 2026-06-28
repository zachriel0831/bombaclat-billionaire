---
name: weekly-macro-line-brief
description: Build market-analysis and weekly-summary prompts for Taiwan investors from relay events, market context, scorecard, RAG analogues, and fixed-watchlist rules. Use when changing macro weekly summary, daily market analysis prompt assets, LINE brief shape, section contracts, or prompt safety rules in data-collecting.
---

# Weekly Macro Summary Skill

This folder is both a repo-local skill and a prompt asset source consumed by `event_relay.weekly_summary` and `event_relay.market_analysis`.

Read [SKILLS.md](SKILLS.md) for the compatibility prompt asset body. Keep both files aligned when editing this skill because older code paths still default to `skills/macro-weekly-summary-skill/SKILLS.md`.

Tone target: professional-but-conversational Taiwan macro commentary. Keep the macro mechanism, but make every indicator answer what the market is trading and why it matters for Taiwan investors; avoid unexplained acronym piles and over-simplified beginner summaries.

Prompt safety: visible reports must not include internal event IDs, source row IDs, citation-only numeric lists, internal pipeline labels, or custom numeric handles. Do not show terms such as `market scorecard`, `scorecard +4`, `market_context`, `market_context:scorecard`, `analysis_slot`, `scheduled_time_local`, `raw_json`, or `07:20 market_context`; translate them into reader-facing Traditional Chinese market implications instead. Keep raw references in `raw_json` telemetry and structured evidence fields.

Current daily `market_analysis` editorial contract lives in [SKILLS.md](SKILLS.md): visible reports start with `今日一句話` and exactly three `三個檢查點`, then move through macro/liquidity, cycle, international-news transmission, industry/sector analysis, and risks/data gaps. Daily reports must not include a dedicated `台股配置` section or append `## 今日個股觀察`; individual companies should appear only as mega-cap transmission examples such as NVIDIA, TSMC, or Magnificent Seven / 美股七巨頭.
