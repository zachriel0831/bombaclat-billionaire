---
name: weekly-macro-line-brief
description: Build market-analysis and weekly-summary prompts for Taiwan investors from relay events, market context, scorecard, RAG analogues, and fixed-watchlist rules. Use when changing macro weekly summary, daily market analysis prompt assets, LINE brief shape, section contracts, or prompt safety rules in data-collecting.
---

# Weekly Macro Summary Skill

This folder is both a repo-local skill and a prompt asset source consumed by `event_relay.weekly_summary` and `event_relay.market_analysis`.

Read [SKILLS.md](SKILLS.md) for the compatibility prompt asset body. Keep both files aligned when editing this skill because older code paths still default to `skills/macro-weekly-summary-skill/SKILLS.md`.

Tone target: professional-but-conversational Taiwan macro commentary. Keep the macro mechanism, but make every indicator answer what the market is trading and why it matters for Taiwan investors; avoid unexplained acronym piles and over-simplified beginner summaries.
