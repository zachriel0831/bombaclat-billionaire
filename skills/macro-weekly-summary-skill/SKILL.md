---
name: weekly-macro-line-brief
description: Guide Codex-owned market-analysis writing for Taiwan investors from recent event facts, market context, and RAG analogues. Use when changing daily market-analysis style, LINE brief shape, section contracts, or prompt safety rules in data-collecting.
---

# Weekly Macro Summary Skill

This folder is a repo-local guidance skill for Codex-owned analysis writing. The old Python LLM daily/weekly generators were retired and no longer consume these files.

Read [SKILLS.md](SKILLS.md) for the compatibility guidance body. Keep both files aligned when editing this skill.

## Research Knowledge Base

`SKILLS.md` now carries a web-checked source hierarchy for macro and world-situation analysis:

- Official data first: Fed/FRED, BLS, BEA, Treasury, IMF, World Bank, OECD, BIS, EIA, WTO, UN Comtrade, and NY Fed GSCPI.
- Risk gauges second: EPU, GPR/TPU, World Uncertainty Index, ACLED, UCDP, GDELT, ReliefWeb, CFR Global Conflict Tracker, and CrisisWatch.
- Interpretation last: IMF/BIS reports, central-bank communication, Brookings, CFR, and Crisis Group.

Use these as verification and reasoning targets when web search is available. Local event rows still anchor the prompt; unsupported hard facts must be lowered in confidence or omitted.

## Analyst Voice Patterns

`SKILLS.md` also carries blended public analyst voice patterns from high-recognition macro, valuation, geopolitical, market-cycle, plain-English finance, dashboard-style, and Taiwan finance-column sources.

Use the patterns as house style only: explain mechanisms, second-order effects, scenarios, policy constraints, narrative-plus-numbers, and Taiwan transmission. Do not imitate a single living writer or copy signature phrasing.

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

`今日一句話` -> `三個檢查點` -> `市場押注與預期差` -> `國際消息到台股的傳導` -> `看錯的條件` -> `備註`

- `三個檢查點` must contain exactly three bullets.
- Each evidence bullet should connect source fact -> mechanism -> why it matters now.
- `市場押注與預期差` should name what is already reflected in prices and what can still be repriced.
- `看錯的條件` means the evidence or market moves that would invalidate the thesis; it is not a buy/sell trigger list.
- Trial trigger-first style: section 1 may start with `結論先講`; section 3 may add `先看區間邊界` with evidence-backed index/rates/FX/SOX levels; section 5 may add `現在只看 N 件事`, where N is the needed count of evidence-backed triggers. Do not force exactly two.
- Do not include a dedicated `台股配置` section.
- Do not append `今日個股觀察`.
- Do not write stock recommendations, buy candidates, or watchlist candidates in visible daily `market_analysis`.
- Individual companies should appear only as mega-cap transmission examples such as NVIDIA, TSMC, or Magnificent Seven / 美股七巨頭, never as recommendations.
- Do not write `開多`, `開空`, `止盈`, `止損`, `入場區間`, or order-level commands in visible daily text; triggers are observation boundaries, not trading instructions.
- If evidence is stale or thin, lower confidence and describe observation limits in reader-facing language. Do not expose missing-data implementation notes.

Pushed daily reports should usually land around 800-1400 Chinese characters. Shorter close digests are acceptable only when the window is thin and the required section order still exists.

## Review Checklist Before Push

- No mojibake.
- No raw slot names, model names, table/API names, guard names, or quota/fallback notes.
- No custom score labels like `scorecard +4`.
- No entry, stop, target, or broker-action language.
- Every market claim is supported by supplied local evidence, externally verified evidence, or clearly framed as an observation limit.
