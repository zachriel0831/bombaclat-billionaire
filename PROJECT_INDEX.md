# data-collecting Project Index

This is the navigation map for the `data-collecting` repo. Use it before opening many files; the repo contains README material, specs, memory-bank history, runbooks, skills, tasks, scripts, and generated runtime artifacts.

## What This Repo Owns

- News and market-data ingestion from RSS, SEC, TWSE/MOPS, X, market-context sources, Taiwan society/politics feeds, and public-record sources.
- Free Palestine English issue-news collection for the public `/timeline` module, stored long-term in `t_palestine_news_items`.
- Official U.S. macro release-calendar collection for CPI, PPI, nonfarm payrolls, and retail sales reminders.
- Heavyweight-stock earnings release-calendar collection for day-before LINE reminders.
- Event relay storage into MySQL tables such as `t_relay_events`, `t_x_posts`, `t_market_index_snapshots`, and `t_market_analyses`.
- Scheduled and manual AI market analysis, weekly summary generation, RAG indexing, claim verification, and fixed-watchlist trade-signal extraction.
- Four-hour Codex-generated cross-section news digest context and Redis publish helpers.
- Taiwan society/politics article collection, keyword extraction, topic classification, public-record ingestion, and article-record linking.
- Engineering memory: architecture, workflows, decisions, lessons, and skill definitions.

## What This Repo Does Not Own

| Capability | Owning repo |
|---|---|
| Public REST/SSE API | `D:/work_space/claude-box/workspace/news-platform-api` |
| Public frontend | `D:/work_space/claude-box/workspace/news-display-frontend` |
| LINE webhook and LINE delivery | `D:/work_space/claude-box/workspace/line-relay-service` |
| Live quote WebSocket monitoring and candle Redis publish | `D:/work_space/claude-box/workspace/stock-monitor-service` |
| Broker order execution | `D:/work_space/claude-box/workspace/order-dispatcher-service` |

## First Files To Read

| Situation | File |
|---|---|
| You need the repo overview | [README.md](README.md) |
| You need Codex/Claude operating rules | [AGENTS.md](AGENTS.md), [CLAUDE.md](CLAUDE.md) |
| You need the architecture and data-flow map | [memory-bank/PROJECT_DOCUMENTATION.md](memory-bank/PROJECT_DOCUMENTATION.md) |
| You need the active memory-bank index | [memory-bank/00-index.md](memory-bank/00-index.md) |
| You need operational workflows | [memory-bank/workflows.md](memory-bank/workflows.md) |
| The machine restarted or services are down | [memory-bank/restart-recovery-runbook.md](memory-bank/restart-recovery-runbook.md) |
| You are changing RAG indexing, retrieval, embeddings, or telemetry | [memory-bank/rag-operations.md](memory-bank/rag-operations.md) |
| You are changing source ingestion or analysis behavior | [memory-bank/rules.md](memory-bank/rules.md) |
| You need active work state | [tasks/todo.md](tasks/todo.md) |
| You need repeated correction history | [tasks/lessons.md](tasks/lessons.md) |

## Specs

| Area | Files |
|---|---|
| Dynamic intraday / short-swing trade candidates | [spec/market-analysis-dynamic-trade-candidates.md](spec/market-analysis-dynamic-trade-candidates.md). The older fixed-watchlist specs remain only as superseded redirects. |
| Taiwan society/politics topic classification | [spec/news-topic-classification-functional-spec.md](spec/news-topic-classification-functional-spec.md), [spec/news-topic-classification-data-contract.md](spec/news-topic-classification-data-contract.md), [spec/news-topic-classification-operations.md](spec/news-topic-classification-operations.md) |
| Taiwan politics second-layer topics and event threads | [spec/political-topic-thread-technical-plan.md](spec/political-topic-thread-technical-plan.md), [spec/political-event-threads/_template.md](spec/political-event-threads/_template.md) |
| Taiwan public-record records and links | [spec/news-public-records-data-contract.md](spec/news-public-records-data-contract.md) |
| NEWS lightweight requirement ledger | [spec/NEWS-INDEX.md](spec/NEWS-INDEX.md), [spec/NEWS-1-author-coverage-and-reporter-relations.md](spec/NEWS-1-author-coverage-and-reporter-relations.md) |
| Free Palestine issue-news scheduled crawl | [spec/NEWS-6-free-palestine-news-scheduled-crawl.md](spec/NEWS-6-free-palestine-news-scheduled-crawl.md) |
| U.S. macro release calendar reminders | [spec/NEWS-5-us-macro-release-calendar-reminders.md](spec/NEWS-5-us-macro-release-calendar-reminders.md) |
| Heavyweight earnings calendar reminders | [spec/NEWS-7-heavyweight-earnings-calendar-reminders.md](spec/NEWS-7-heavyweight-earnings-calendar-reminders.md) |
| Four-hour AI news digest | [spec/NEWS-9-four-hour-ai-news-digest.md](spec/NEWS-9-four-hour-ai-news-digest.md) |
| News crawler category source list | [spec/news-crawler-category-sources.md](spec/news-crawler-category-sources.md) |

## Memory Bank

| Path | Purpose |
|---|---|
| [memory-bank/PROJECT_DOCUMENTATION.md](memory-bank/PROJECT_DOCUMENTATION.md) | Current architecture, ingestion sources, storage boundaries, analysis policy, scheduler, security, operations. |
| [memory-bank/workflows.md](memory-bank/workflows.md) | Repeatable workflows for source additions, incidents, analysis jobs, retention, market context, and readiness. |
| [memory-bank/restart-recovery-runbook.md](memory-bank/restart-recovery-runbook.md) | Machine restart recovery checklist and done criteria. |
| [memory-bank/rag-operations.md](memory-bank/rag-operations.md) | RAG indexing/retrieval runbook, tables, config, telemetry, and tests. |
| [memory-bank/09-decisions/](memory-bank/09-decisions/) | Architecture and workflow decision records. |
| [memory-bank/pr-review.md](memory-bank/pr-review.md) and [memory-bank/20-pr-review-standards.md](memory-bank/20-pr-review-standards.md) | Review format and review priorities. |
| [memory-bank/archive/enterprise/](memory-bank/archive/enterprise/) | Archived enterprise-agent governance references. |

## Skills

| Path | Purpose |
|---|---|
| [skills/README.md](skills/README.md) | Skill workspace structure. |
| [skills/news-ingestion-skill/SKILL.md](skills/news-ingestion-skill/SKILL.md) | Ingestion workflow skill. |
| [skills/rag-operations-skill/SKILL.md](skills/rag-operations-skill/SKILL.md) | Historical-case RAG operating skill. |
| [skills/political-topic-thread-skill/SKILL.md](skills/political-topic-thread-skill/SKILL.md) | Taiwan politics topic/thread workflow skill. |
| [skills/macro-weekly-summary-skill/SKILL.md](skills/macro-weekly-summary-skill/SKILL.md) | Weekly summary and market-analysis prompt workflow guidance. |
| [skills/line-brief-format-skill/](skills/line-brief-format-skill/) | LINE brief formatting references. |
| [skills/templates/](skills/templates/) | Templates for new skills, evals, and changelogs. |

## Runtime And Script Entry Points

| Task | Command or script |
|---|---|
| Run relay service | `powershell -ExecutionPolicy Bypass -File .\scripts\run_event_relay.ps1` |
| Run source bridge | `powershell -ExecutionPolicy Bypass -File .\scripts\run_source_bridge.ps1 -PollIntervalSeconds 300 -Limit 5` |
| Run local console | `powershell -ExecutionPolicy Bypass -File .\scripts\run_local_console.ps1` |
| Data-source health report | `powershell -ExecutionPolicy Bypass -File .\scripts\run_data_source_health.ps1 -EnvFile .env` |
| Market analysis | `powershell -ExecutionPolicy Bypass -File .\scripts\run_market_analysis.ps1 -Slot pre_tw_open -Force` |
| Weekly summary | `powershell -ExecutionPolicy Bypass -File .\scripts\run_weekly_summary.ps1 -Force -DryRun` |
| Market context | `powershell -ExecutionPolicy Bypass -File .\scripts\run_market_context.ps1 -EnvFile .env` |
| Free Palestine English issue news | `powershell -ExecutionPolicy Bypass -File .\scripts\run_palestine_news.ps1 -EnvFile .env -Limit 20` |
| Four-hour digest context | `powershell -ExecutionPolicy Bypass -File .\scripts\run_four_hour_digest_context.ps1 -EnvFile .env -Hours 4 -OutFile runtime\four-hour-digest\context.json` |
| Four-hour digest Redis store | `powershell -ExecutionPolicy Bypass -File .\scripts\store_four_hour_digest_to_redis.ps1 -InputFile runtime\four-hour-digest\digest.json -TtlSeconds 15000` |
| CWA typhoon/earthquake records | `powershell -ExecutionPolicy Bypass -File .\scripts\run_cwa_weather.ps1 -EnvFile .env` |
| U.S. macro release calendar | `powershell -ExecutionPolicy Bypass -File .\scripts\run_macro_calendar.ps1 -EnvFile .env` |
| RAG indexing | `powershell -ExecutionPolicy Bypass -File .\scripts\run_rag_indexer.ps1 -EnvFile .env` |
| Retention cleanup | `powershell -ExecutionPolicy Bypass -File .\scripts\run_retention_cleanup.ps1 -EnvFile .env` |

## Source Tree Map

| Path | Purpose |
|---|---|
| `src/news_collector/` | RSS, SEC, TWSE/MOPS, X, and relay bridge ingestion. |
| `src/event_relay/` | HTTP relay, MySQL event storage, market analysis, weekly summary, RAG, market context, trade signals. |
| `src/news_platform/` | Taiwan society/politics article collection, topic classification, public records, matching. |
| `src/data_source_health.py` | Freshness and local process health checks. |
| `tests/` | Unit and integration-style tests for ingestion, relay, analysis, public records, topic classification, and health checks. |
| `runtime/` | Generated logs, prompt snapshots, eval notes, and local runtime artifacts. |

## Documentation Rules

- README is the public entry point.
- This index is the navigation layer.
- `spec/` is for product specs and data contracts.
- `memory-bank/` is for architecture, workflows, runbooks, decisions, and historical operating context.
- `skills/` is for agent-operating instructions, not the only source of service truth.
- When architecture, data flow, source mapping, or alert behavior changes, update README or this index plus the relevant memory-bank/spec file.
