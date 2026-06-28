# Codex Market-Analysis Guard Automations

## Context

The scheduled `data-collecting` market-analysis pipeline can fail or become
delivery-blocked when provider quota is exhausted, a provider schema stage
fails, or `claim_verifier` flags fixable visible tokens. The platform already
pays for Codex Pro, while OpenAI API quota is a separate paid surface.

## Decision

Create Codex cron guard automations after the existing market-analysis windows:

- `market-analysis-codex-guard-us-close`
- `market-analysis-codex-guard-pre-open`
- `market-analysis-codex-guard-tw-close`

These guards are agent jobs. They inspect the scheduled analysis row, leave
healthy rows unchanged, and repair only when needed using local DB evidence,
repo skills/templates, deterministic `claim_verifier`, and
`MySqlEventStore.upsert_market_analysis`. When scheduled Python LLM prose
generation is disabled, the same guards may create the missing prose row from
local evidence.

The guard prompts explicitly forbid OpenAI API, Anthropic API, or other paid
external LLM API calls. Repaired rows must store telemetry that indicates
`external_provider_api_called=false`.

## Consequences

- Data collection, market context, RAG, BLS, Taiwan market-flow, and retention
  tasks remain scheduled.
- Scheduled Python LLM prose-generation tasks may be disabled for cost control:
  `NewsCollector-MarketAnalysis-UsClose`,
  `NewsCollector-MarketAnalysis-PreTwOpen`,
  `NewsCollector-MarketAnalysis-TwClose`, and
  `NewsCollector-WeeklySummary`.
- Codex guards provide a lower-cost generation/repair path after provider
  quota/schema failures or when the Python prose task is disabled.
- Delivery stays Java-owned: `push_enabled` follows existing policy and
  `pushed` remains false unless line-relay marks successful delivery.
- The guards are not deterministic services; each run must verify DB state and
  keep a concise run report.
- Long-term code fixes are still needed for recurring schema or verifier false
  positives.
