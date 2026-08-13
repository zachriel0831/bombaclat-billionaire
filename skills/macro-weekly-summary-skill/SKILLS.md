---
name: weekly-macro-line-brief
description: Guide Codex-owned market-analysis writing for Taiwan investors from recent event facts, market context, and RAG analogues. Use when changing daily market-analysis style, LINE brief shape, section contracts, or prompt safety rules in data-collecting.
---

# Weekly Macro Summary Skill

This file is intentionally retained for compatibility with existing guidance links. Keep it in sync with `SKILL.md` when editing this skill.

## Purpose

Guide Codex-generated market-analysis drafts so they are evidence-grounded, readable in LINE, and useful for Taiwan investors.

## Inputs

- Recent local relay event source facts.
- Stored market-context facts and deterministic market signal rows.
- Recent market index snapshots when available.
- Hybrid RAG historical analogues from embeddings.

## External Research Knowledge Base

Use this hierarchy when web search is available. Local rows remain the primary
evidence pack; these sources are verification and interpretation targets, not a
reason to fabricate missing facts.

1. Official macro / market data
- Fed / FRED, BLS, BEA, U.S. Treasury Fiscal Data, IMF Data / WEO, World Bank
  Data360, OECD Data Explorer, BIS Data Portal, EIA, WTO, UN Comtrade, and New
  York Fed GSCPI.

2. Uncertainty / geopolitical event data
- Economic Policy Uncertainty, Geopolitical Risk / Trade Policy Uncertainty,
  World Uncertainty Index, ACLED / CAST, UCDP, GDELT, ReliefWeb, CFR Global
  Conflict Tracker, and International Crisis Group CrisisWatch.

3. Research interpretation layer
- IMF WEO / GFSR / Fiscal Monitor, BIS Quarterly Review, central-bank speeches
  and minutes, Brookings Global Economy, CFR backgrounders, and Crisis Group
  conflict notes. Use these for mechanisms and risk maps; cross-check hard
  numbers against official data sources above.

## Analysis Skills

- Regime map: growth, inflation, policy reaction function, liquidity, credit,
  risk appetite, and positioning.
- Surprise lens: separate consensus / already-priced facts from new
  information that can still reprice rates, FX, commodities, semis, financials,
  or cyclicals.
- Transmission chain: source fact -> macro or geopolitical mechanism -> U.S.
  assets / USD / rates / oil / SOX -> Taiwan index, sectors, and mega-cap
  proxies.
- Geopolitical escalation ladder: event -> chokepoint, sanctions, shipping,
  energy, defense, or supply-chain channel -> market risk premium.
- Evidence discipline: one concrete claim needs local evidence, official data,
  or externally verified support; news-volume indices are risk gauges, not
  direct proof of economic damage.

## Popular Analyst Voice Patterns

Blend these public analyst patterns into the house voice. Do not imitate any
single living writer, copy signature phrases, or quote paid/public articles.

- Ray Dalio pattern: explain the "machine" first. Link debt, credit,
  productivity, policy, and asset prices before giving a market conclusion.
- Howard Marks pattern: use second-level thinking. State what the consensus
  already believes, then what second-order risk, cycle, or psychology it may be
  underpricing.
- Mohamed El-Erian pattern: write in scenarios. Separate baseline, downside
  tail, and policy constraint; name where resilience can turn into fragility.
- Lyn Alden pattern: trace the plumbing. Connect fiscal stance, liquidity,
  rates, FX, energy, and balance sheets into cross-asset implications.
- Marko Papic pattern: geopolitics is constraints over preferences. Ask what
  policymakers can actually do under voters, budgets, alliances, energy, and
  market pressure.
- Aswath Damodaran pattern: every narrative needs numbers. Tie any sector or
  company story to measurable revenue, margin, multiple, cash-flow, or macro
  driver.
- Ben Carlson pattern: make the complex sound simple without dumbing it down.
  Use short sanity checks and avoid false precision.
- Yardeni / data-dashboard pattern: use chart-led quick takes. Start from the
  strongest indicator, then say whether earnings, inflation, liquidity, or
  valuation confirms it.
- Taiwan finance-column pattern: translate global shocks into Taiwan's export,
  FX, semiconductor, financial, energy-cost, and policy-negotiation channels.

Reusable phrasing shapes:

- "市場現在交易的不是 A 本身，而是 A 會不會改變 B。"
- "第一層看起來是 X，第二層真正要看的是 Y。"
- "已反映的是 X，還沒完全反映的是 Y。"
- "這條傳導鏈是：事件 -> 價格/政策 -> 產業 -> 台股。"
- "破局條件很乾淨：如果 X 沒出現，這個判斷就要降級。"

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
- Do not write Taiwan ticker recommendations, watchlist candidates, entry plans, stop-loss levels, or target-price lists.
- Daily visible reports must focus on macro and industry/sector interpretation. Mention individual companies only as mega-cap transmission examples such as NVIDIA, TSMC, or Magnificent Seven / 美股七巨頭.
- Pushed daily reports should usually land around 800-1400 Chinese characters; shorter close digests are acceptable only when the window is thin and all required sections still exist.
- Do not output order intents, broker actions, or automated trading instructions.

## Daily Market Analysis Sections

Use this readable author-style macro flow unless the calling code supplies a stricter section contract:

1. 今日一句話
2. 三個檢查點
3. 市場押注與預期差
4. 國際消息到台股的傳導
5. 看錯的條件
6. 備註

`三個檢查點` should contain exactly three bullets. Each bullet should connect source fact -> mechanism -> why it matters now. `市場押注與預期差` should name what is already reflected in prices and what can still be repriced. `看錯的條件` means the evidence or market moves that would invalidate the thesis; it is not a buy/sell trigger list.

For daily `market_analysis`, do not append `今日個股觀察`, do not write `台股配置` as a visible section, and do not write stock recommendations, buy candidates, watchlist candidates, `stock_watch`, entry plans, stop-loss levels, or target-price lists. The visible report may mention companies such as NVIDIA, TSMC, or Magnificent Seven / 美股七巨頭 only to explain macro/sector transmission.

Trial trigger-first style: section 1 may start with `結論先講`; section 3 may add `先看區間邊界` with evidence-backed index/rates/FX/SOX levels; section 5 may add `現在只看 N 件事`, where N is the needed count of evidence-backed triggers. Do not force exactly two. Do not write `開多`, `開空`, `止盈`, `止損`, `入場區間`, or order-level commands in visible daily text; triggers are observation boundaries, not trading instructions.

## Weekly Summary Sections

Weekly reports use:

1. 週總經
2. 下週台股配置
3. 下週觀察清單

Weekly reports are allocation/watchlist briefs. They should not produce intraday entry, take-profit, stop-loss, or order-level instructions.

## Related Docs

- [../../memory-bank/rag-operations.md](../../memory-bank/rag-operations.md)
- [../line-brief-format-skill/line-weekly-brief.md](../line-brief-format-skill/line-weekly-brief.md)
- [../line-brief-format-skill/rubric.md](../line-brief-format-skill/rubric.md)
