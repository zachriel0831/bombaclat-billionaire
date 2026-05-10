# Decision: OpenAI-First LLM Topic Fallback

## Context
Rule classification is cheap and predictable, but it misses contextual follow-up headlines where the issue is implied by title/summary rather than explicit keywords.

## Decision
Add an optional LLM fallback layer for Taiwan society topic classification.

Default provider order:
1. OpenAI `gpt-5-nano`
2. Anthropic Claude Haiku `claude-haiku-4-5-20251001`

The fallback is disabled by default and runs only for rows where deterministic classification produced `general_social_news` and `topic_classified_by` is NULL or `rule`.

## Storage
- LLM matched topic: write one topic object with `source="llm"`, `provider`, `model`, and `reason`
- LLM no-match: keep `general_social_news` with `source="llm_fallback"` and set `topic_classified_by="llm"`
- This prevents repeated calls on rows that already failed both layers

## Rationale
- OpenAI GPT-5 nano is the lowest-cost OpenAI GPT-5 variant and is explicitly suitable for classification tasks.
- Claude Haiku 4.5 is Anthropic's fastest current Haiku model and is used only when OpenAI is unavailable.
- Keeping the fallback optional lets production measure rule miss volume before enabling paid calls.
