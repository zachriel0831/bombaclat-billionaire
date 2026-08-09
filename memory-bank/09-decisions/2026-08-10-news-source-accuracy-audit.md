# 2026-08-10 News Source Accuracy Audit

## Decision
Add a scheduled official-list coverage audit for Taiwan society/politics news sources.

## Context
- Freshness checks only prove that rows arrive in MySQL; they do not prove that our stored rows are close to what source sites currently advertise.
- Some sources expose stable RSS/sitemap feeds, while TVBS/UDN/SETN are intentionally low-frequency public HTML list supplements.
- CTEE public endpoints still return 403 locally and should not be bypassed with rotating user agents, cookies, or proxies.

## Consequences
- `scripts/run_news_source_accuracy_audit.ps1` compares current official-list items with `t_news_articles` by `article_id` or canonical URL.
- Default audit scope is active sources plus TVBS/UDN/SETN, skipping CTEE.
- Scheduled task `NewsCollector-NewsSourceAccuracyAudit` runs every 2 hours by default with compensation enabled.
- Compensation is limited to one bounded existing crawler pass for sources below the coverage threshold, followed by deterministic keyword/topic enrichment. It does not push LINE messages, generate prose, or call LLMs.
- If coverage remains below threshold after compensation, the run exits non-zero and Observer records a failed `news_source_accuracy_audit` event.
