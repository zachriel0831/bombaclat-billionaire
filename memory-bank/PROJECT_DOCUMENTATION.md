# Project Documentation

## Project Goal
Collect breaking international finance news from multiple upstreams, normalize records, and prepare data for downstream alerting (LINE Bot and group notifications in later phases).

## Current Architecture
- Language: Python 3.10+
- Package: `src/news_collector`
- Entry point: `python -m news_collector.main fetch ...`
- Output: normalized JSON lines or pretty JSON array

## Source Adapters
1. Official RSS (`official_rss`)
- Default feeds:
  - Federal Reserve
  - ECB
  - BIS
- Auth: no API key
- File: `src/news_collector/sources/rss.py`

2. GDELT (`gdelt`)
- Endpoint: DOC 2.0 ArtList mode
- Auth: no API key
- Notes: includes simple retry for rate-limit errors
- File: `src/news_collector/sources/gdelt.py`

3. Benzinga (`benzinga`)
- Endpoint: `/api/v2/news`
- Auth: requires `BENZINGA_API_KEY`
- File: `src/news_collector/sources/benzinga.py`

## Normalized Schema
- `id`: stable ID string
- `source`: source name
- `title`: headline/title
- `url`: original article URL
- `published_at`: ISO-8601 timestamp (UTC offset preserved if available)
- `summary`: short description/snippet
- `tags`: source tags/symbols/channels
- `raw`: original source payload

## Runtime Configuration
Environment variables:
- `BENZINGA_API_KEY` (required for `benzinga`)
- `GDELT_QUERY` (optional)
- `GDELT_MAX_RECORDS` (optional)
- `OFFICIAL_RSS_FEEDS` (optional, comma-separated URLs)
- `HTTP_TIMEOUT_SECONDS` (optional)

## Non-Goals (Current Phase)
- No persistent storage yet
- No dedupe cache across process restarts
- No LINE Bot delivery yet
- No vendor-specific SLA monitoring yet

## Enterprise Readiness Assets
- Agent readiness baseline:
  - `memory-bank/40-agent-enterprise-readiness.md`
- Skills engineering standard:
  - `memory-bank/41-skills-engineering-standard.md`
- Evaluation and release gates:
  - `memory-bank/42-agent-evals-and-release-gates.md`
- Security and compliance baseline:
  - `memory-bank/43-agent-security-and-compliance.md`
- MCP governance:
  - `memory-bank/44-mcp-server-governance.md`
- Skills registry and templates:
  - `skills/registry.yaml`
  - `skills/templates/`
- Automated readiness validation:
  - `scripts/validate_readiness.py`
  - `.github/workflows/readiness-gate.yml`
