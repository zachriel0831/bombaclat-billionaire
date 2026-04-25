# Decision: News Topic Taxonomy, Trade-Impact Tags, Cluster ID

## Date
2026-04-25

## Context
REQ-020 lifts existing news collection from "we have a row in `t_relay_events`"
to "we have a structured trade signal the analysis pipeline can consume
directly". Without this layer:
- Stage1 spends tokens re-deriving topic/region/direction every run.
- Same wire story from BBC, Reuters, AP shows up as three independent
  bullish/bearish votes.
- The pipeline can't tell whether a headline is a single-name catalyst
  (TSMC earnings) or a broad-market factor (FOMC decision).

REQ-013 already provides entities/category/importance/sentiment. REQ-020
layers a finer-grained topic taxonomy plus trade-relevant tags on top.

## Decision

### Two-layer composition (REQ-013 + REQ-020)
- REQ-013 stays as the base annotation (`EventAnnotation`).
- REQ-020 adds `NewsImpact` (separate dataclass) computed by
  `derive_news_impact(annotation, title, summary, raw_json)`. No mutation
  of REQ-013 surface.

### Topic taxonomy (10 values)
`geopolitics`, `macro`, `central_bank`, `semiconductor`, `ai`, `supply_chain`,
`energy`, `regulation`, `corporate_action`, `other`.

Earlier rule wins on tie. Order is deliberate so e.g. a regulation event in
the chip space lands in `semiconductor`, not `regulation`. The taxonomy is
finer than REQ-013 `category` but they coexist — `category` stays for
backward compatibility and broader stage1 schema.

### Impact tags
| Field | Values | Derivation |
|---|---|---|
| `impact_region` | `US` `TW` `CN` `EU` `JP` `KR` `Global` | Most-mentioned country entity. Multiple distinct countries → `Global`. No country → `Global`. |
| `impact_scope` | `index` `sector` `single_name` | Has ticker / company entity → `single_name`. Topic in {semiconductor, ai, energy, supply_chain} → `sector`. Otherwise → `index`. |
| `impact_direction` | `bullish` `bearish` `mixed` `unknown` | Aliases REQ-013 sentiment. Falls to `unknown` when no entities and importance < 0.3. Neutral with entities → `mixed`. |
| `urgency` | `low` `medium` `high` | Topic-driven (central_bank/geopolitics → high) plus importance threshold. |
| `confidence` | `low` `medium` `high` | Importance >= 0.7 with entities → `high`; importance >= 0.4 → `medium`; else `low`. |
| `data_gap` | bool | True when category=`other`, no entities, or importance < 0.3. |

### Cluster ID
`compute_cluster_id(title, summary=...)` — stable 12-char SHA-1 prefix.
Algorithm:
1. Strip wire-service prefix (Reuters / Bloomberg / AP / BBC / CNBC / WSJ /
   FT / Nikkei / 新華社 / 中央社).
2. Tokenise on `[A-Za-z0-9一-鿿]+`, lowercase.
3. Drop short / stop-word tokens.
4. Hash sorted token-set.

Same headline from different wires → same cluster. Token reordering with
identical word forms → same cluster. Different paraphrasing (`cut` vs
`cuts`) → different cluster — accepted v1 limitation. Stemming / fuzzy
similarity is deferred until duplicate analysis becomes a measurable issue.

### Pipeline integration
`_build_events_payload` (in `market_analysis.py`) now calls
`derive_news_impact` per event and adds `impact` next to the existing
`annotation` field. Stage1 prompt receives the JSON unchanged, so the LLM
sees impact tags without prompt edits. Deeper prompt tuning (e.g.
"prioritise events with `urgency=high` and `data_gap=false`") is left to
follow-up tickets so this REQ stays scoped to data plumbing.

## Consequences
- Cluster id is *advisory*, not a uniqueness key. Multiple rows can share a
  cluster id; downstream consumers can dedupe or aggregate.
- `data_gap=true` is a hint to stage1, not a filter. Stage1 already produces
  `data_gaps` in its output; this just gives it an upstream signal.
- Adding fields to `EventAnnotation` would have rippled through stage1
  schema enums and stored annotation rows. Keeping `NewsImpact` separate
  avoids that migration churn.
- The taxonomy is a heuristic. When ambiguous (e.g. an FOMC rate cut on
  semiconductor outlook), `central_bank` wins because the rate move
  dominates the trade signal. Re-tune the rule order if the analysis output
  is misclassifying a recurring case.

## Alternatives considered
- **Embed impact fields directly inside `EventAnnotation`.** Rejected:
  forces a stored-annotation schema migration and a stage1 schema enum
  expansion; v1 doesn't need the extra rigidity.
- **Server-side LLM classifier per event.** Rejected for v1: cost-prohibitive
  on the relay ingest path. Rule-based path is deterministic, free, and good
  enough as a prior. LLM upgrade can swap the function in place if needed.
- **Cluster by exact title hash only.** Rejected: misses simple variants
  like prefix changes. Token-set hash catches the most common dup pattern
  (same content, different wire prefix) at no extra cost.

## Verification
- `tests/test_news_impact.py` — 26 tests across topic taxonomy, region/scope,
  direction/urgency/confidence, contract enums, cluster id semantics.
- Full suite: 196 green.
