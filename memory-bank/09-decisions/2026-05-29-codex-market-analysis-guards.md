# Codex Market-Analysis Guard Automations

## Context

The scheduled `data-collecting` market-analysis pipeline can fail or become
delivery-blocked when provider quota is exhausted, a provider schema stage
fails, or `claim_verifier` flags fixable visible tokens. The platform already
pays for Codex Pro, while OpenAI API quota is a separate paid surface.

Superseded 2026-08-13: the Python LLM daily/weekly analysis generators are
retired and removed. Codex automations are now the owner of analysis prose, not
a fallback for scheduled Python LLM tasks.

## Decision

Create Codex cron guard automations after the existing market-analysis windows:

- `market-analysis-codex-guard-us-close`
- `market-analysis-codex-guard-pre-open`
- `market-analysis-codex-guard-tw-close`

These guards are agent jobs. They inspect the scheduled analysis row, leave
healthy rows unchanged, and repair only when needed using local DB evidence,
repo skills/templates, deterministic `claim_verifier`, and
`MySqlEventStore.upsert_market_analysis`. Because Python LLM prose generation
is retired, Codex automations may create the missing prose row from local
evidence.

The guard prompts explicitly forbid OpenAI API, Anthropic API, or other paid
external LLM API calls. Repaired rows must store telemetry that indicates
`external_provider_api_called=false`.

## Consequences

- Data collection, market context, RAG, BLS, Taiwan market-flow, and retention
  tasks remain scheduled.
- Scheduled Python LLM prose-generation tasks must not exist:
  `NewsCollector-MarketAnalysis-UsClose`,
  `NewsCollector-MarketAnalysis-PreTwOpen`,
  `NewsCollector-MarketAnalysis-TwClose`, and
  `NewsCollector-WeeklySummary`.
- Codex guards provide the generation/repair path for analysis prose.
- Delivery stays Java-owned: `push_enabled` follows existing policy and
  `pushed` remains false unless line-relay marks successful delivery.
- The guards are not deterministic services; each run must verify DB state and
  keep a concise run report.
- Long-term code fixes are still needed for recurring schema or verifier false
  positives.
