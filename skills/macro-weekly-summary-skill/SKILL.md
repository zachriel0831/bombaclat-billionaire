---
name: weekly-macro-line-brief
description: Build market-analysis and weekly-summary prompts for Taiwan investors from recent event facts, market context, RAG analogues, and fixed-watchlist rules. Use when changing macro weekly summary, daily market analysis prompt assets, LINE brief shape, section contracts, or prompt safety rules in data-collecting.
---

# Weekly Macro Summary Skill

This folder is both a repo-local skill and a prompt asset source consumed by `event_relay.weekly_summary` and `event_relay.market_analysis`.

Read [SKILLS.md](SKILLS.md) for the compatibility prompt asset body. Keep both files aligned when editing this skill because older code paths still default to `skills/macro-weekly-summary-skill/SKILLS.md`.

## Tone Target

Write like a professional-but-conversational Taiwan macro commentator. Keep the market mechanism, but make every indicator answer:

- What is the market trading now?
- Why does this evidence matter?
- How does it transmit into Taiwan equities, sectors, or major proxies?
- What would invalidate the thesis?

Avoid unexplained acronym piles and beginner-style lazy summaries.

## Prompt Safety

Visible reports must not include internal event IDs, source row IDs, citation-only numeric lists, internal pipeline labels, table names, API/guard implementation notes, provider names, quota notes, or custom numeric handles.

Do not show internal source labels, table names, snake_case fields, scheduled task names, provider names, guard names, or custom score labels.

Translate those into reader-facing Traditional Chinese market implications instead. Keep raw references only in telemetry and structured evidence fields.

## Daily Market Analysis Contract

Visible daily reports use:

`今日主命題` -> `三個證據` -> `市場正在定價什麼` -> `台股傳導` -> `反證條件` -> `風險與觀察限制`

- `三個證據` must contain exactly three bullets.
- Each evidence bullet should connect source fact -> mechanism -> why it matters now.
- Do not include a dedicated `台股配置` section.
- Do not append `今日個股觀察`.
- Individual companies should appear only as mega-cap transmission examples such as NVIDIA, TSMC, or Magnificent Seven / 美股七巨頭.
- If evidence is stale or thin, lower confidence and describe observation limits in reader-facing language. Do not expose missing-data implementation notes.

Pushed daily reports should usually land around 800-1400 Chinese characters. Shorter close digests are acceptable only when the window is thin and the required section order still exists.

## Review Checklist Before Push

- No mojibake.
- No raw slot names, model names, table/API names, guard names, or quota/fallback notes.
- No custom score labels like `scorecard +4`.
- No entry, stop, target, or broker-action language.
- Every market claim is supported by supplied local evidence, externally verified evidence, or clearly framed as an observation limit.
