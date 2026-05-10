# Decision: Hybrid RAG, Stage0 Tensions, Claim Verification, and Quota-Aware Model Routing

Date: 2026-05-07

## Context

Daily market analysis needs to move closer to thesis-driven macro writing:
- choose the day's main contradiction before drafting
- retrieve useful past cases without confusing them with current evidence
- check final numeric/date/ticker claims against available evidence
- avoid failing or overspending when one LLM provider is out of budget

OpenAI exposes organization cost reporting through `/v1/organization/costs`, and Anthropic exposes Admin API cost reporting through `/v1/organizations/cost_report`. These are cost/usage checks, not perfect per-request remaining quota checks, so local monthly budget thresholds are still required.

References:
- OpenAI API reference: https://platform.openai.com/docs/api-reference/usage/cost
- Anthropic / Claude Admin API reference: https://platform.claude.com/docs/en/api/admin/cost_report/retrieve

## Decision

- RAG retrieval is hybrid:
  - metadata overlap filters candidates
  - deterministic lexical/vector similarity ranks semantic fit
  - stored `outcome_json` contributes an outcome prior
  - event examples and generated-analysis examples can both enter stage2
- Add deterministic `stage0_thesis_selector` before LLM stages.
  - It selects 1-2 current core tensions from scorecard/context.
  - Later stages receive this JSON and must answer those tensions.
- Add `claim_verifier` after generation.
  - It checks numbers, dates, and tickers in final output against prompt evidence.
  - Results are telemetry only for now; they do not block storage.
- Add `llm_quota_router` before analysis execution.
  - Scheduled market analysis is OpenAI-primary and Anthropic/Claude fallback second by default.
  - It selects OpenAI/Anthropic provider and model using configured provider order, model lists, monthly budgets, and Admin API cost checks.
  - If no budget is configured, routing keeps the preferred provider and records `unknown`.
  - If an Admin API check fails, routing continues unless `MARKET_ANALYSIS_REQUIRE_QUOTA_CHECK=true`.
- Add Anthropic compact context policy.
  - When Claude is selected, prompts are compacted by reducing event rows, market rows, RAG examples, raw JSON detail, and long summaries.
  - The policy preserves scorecard, market_context rows, official sources, and high-importance events before general news overflow.

## Consequences

- `t_market_analyses.raw_json` now includes:
  - `model_router`
  - `provider_context_policy`
  - hybrid `rag.score_components`
  - `pipeline_stages.core_tensions`
  - `claim_verifier`
- No schema migration is required.
- Admin API keys are high-sensitivity secrets and must not be logged.
- Cost checks protect budget at provider/month level; they do not guarantee a single large prompt will fit rate limits or prepaid quota.
