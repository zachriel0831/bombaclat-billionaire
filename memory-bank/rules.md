# Project Rules

## Source Priority
1. Official institution feeds
2. Licensed market-news providers
3. Broad crawled aggregators

If two sources conflict, prefer the higher-priority source in output or alert explanation.

## Security Rules
- Never commit real API keys or access tokens.
- Keep secrets in `.env` or CI secrets only.
- Do not print full tokens in logs or error payloads.

## Data Quality Rules
- Preserve source timestamps and normalize parsing consistently.
- Use stable IDs for dedupe keys.
- Keep raw payload for traceability in debugging.
- Do not silently swallow source errors; return explicit error items or logs.

## Coding Rules
- Keep adapters isolated by source.
- Keep shared parsing helpers in `utils.py` and network calls in `http_client.py`.
- Prefer explicit exceptions and user-facing config error messages.
- Add tests for config logic and non-network core behavior.
- For agent/skills changes, run `python scripts/validate_readiness.py`.

## Change Management Rules
- Any schema change requires updating:
  - `README.md`
  - `memory-bank/PROJECT_DOCUMENTATION.md`
- Any new repeatable process requires workflow update:
  - `memory-bank/workflows.md`
- Any user correction requires adding an entry to:
  - `tasks/lessons.md`
- Any new skill requires updating:
  - `skills/registry.yaml`
  - `skills/<skill-name>/SKILL.md`
  - `skills/<skill-name>/EVALS.md`
  - `skills/<skill-name>/CHANGELOG.md`
