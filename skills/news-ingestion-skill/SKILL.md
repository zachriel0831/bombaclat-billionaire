---
name: news-ingestion-skill
description: Maintain, debug, or extend data-collecting ingestion workflows. Use when working on RSS, SEC EDGAR, TWSE/MOPS, X stream/backfill, Taiwan society/politics article sources, public-record sources, relay bridge normalization, source freshness health, or ingestion tests in the data-collecting repo.
---

# News Ingestion Skill

## Purpose

Use this skill to change or operate ingestion paths that collect upstream facts and normalize them into local storage.

## Scope

- Finance/international sources: RSS, SEC EDGAR, TWSE/MOPS, X stream/backfill, U.S. index tracker.
- Market context sources: Yahoo chart proxies, U.S. Treasury, FRED, EIA, BLS, TWSE/TPEx/TAIFEX flows.
- Taiwan public-news product sources: society/politics RSS, sitemap/list crawlers, keyword extraction, topic classification.
- Public records: Legislative Yuan bills, NPA fraud rumors, NPA A1 accident records, article-record matching.

Out of scope:

- LINE delivery: `line-relay-service`.
- Public API serving: `news-platform-api`.
- Live quote WebSocket monitoring: `stock-monitor-service`.
- Broker order execution: `order-dispatcher-service`.

## Default Workflow

1. Read [../../PROJECT_INDEX.md](../../PROJECT_INDEX.md) for repo navigation when cold.
2. Read [../../memory-bank/rules.md](../../memory-bank/rules.md).
3. For source mapping, schema, scheduler, or service-boundary changes, read [../../memory-bank/PROJECT_DOCUMENTATION.md](../../memory-bank/PROJECT_DOCUMENTATION.md).
4. For repeatable source workflows or incidents, read [../../memory-bank/workflows.md](../../memory-bank/workflows.md).
5. Check relevant specs under [../../spec](../../spec) before changing topic/public-record contracts.
6. Keep ingestion failures source-scoped; one failed source must not stop unrelated sources.
7. Update README, specs, memory-bank decisions, or workflows when behavior changes.

## Key Commands

```powershell
$env:PYTHONPATH='src'; python -m news_collector.main fetch --source rss --limit 3 --log-level INFO --pretty
$env:PYTHONPATH='src'; python -m news_collector.main fetch --source sec --limit 10 --pretty
$env:PYTHONPATH='src'; python -m news_collector.main fetch --source twse --limit 10 --pretty
$env:PYTHONPATH='src'; python -m news_platform.main --smoke
powershell -ExecutionPolicy Bypass -File .\scripts\run_data_source_health.ps1 -EnvFile .env
```

## Verification

Use focused tests for the changed path, then broaden when contracts are touched:

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests -p "test_*.py" -v
python scripts/validate_readiness.py
```

## Safety

- Do not print API keys, bearer tokens, `.env` contents, or DPAPI secret payloads.
- Prefer official source APIs and source docs over assumptions.
- Treat `.env` local credentials as owner-approved local-development state; cloud migration must reissue and move secrets to a secret store.
- When user corrections repeat, update `tasks/lessons.md`.
