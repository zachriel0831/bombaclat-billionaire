# Skills Workspace

This folder is the canonical location for repo-local skill assets in this repository. Codex is the primary consumer; Claude may use the same files as supporting context.

## Structure
- `skills/registry.yaml`: global skill registry and ownership
- `skills/templates/`: templates for new skills
- `skills/<skill-name>/`: concrete skill implementation docs and assets
- `skills/rag-operations-skill/`: historical-case RAG operating guidance for agents
- `skills/political-topic-thread-skill/`: Taiwan politics topic and event-thread workflow guidance for agents
- `skills/macro-weekly-summary-skill/` and `skills/line-brief-format-skill/`: prompt assets consumed by analysis jobs; they are not registered enterprise skills and do not own delivery behavior

## Skill Types

- Registered enterprise skills are listed in `skills/registry.yaml` and must have `SKILL.md`, `EVALS.md`, and `CHANGELOG.md`.
- Prompt-asset skills are used by runtime prompt builders. They may keep compatibility filenames when code already loads them, but each should also expose a normal `SKILL.md` entry when practical.
- Formatting references such as `line-brief-format-skill/` are supporting references, not standalone service owners.

## Required files per skill
Registered enterprise skills must include:
- `SKILL.md`
- `EVALS.md`
- `CHANGELOG.md`

Every `SKILL.md` should use YAML frontmatter with `name` and `description`, followed by concise instructions. Put detailed contracts in `spec/` or `memory-bank/` and link them from the skill instead of duplicating long context.

## Quick start
1. Copy templates from `skills/templates/`.
2. Register the skill in `skills/registry.yaml`.
3. Fill required fields and owners.
4. Add eval cases and thresholds.
5. Run readiness validation script:
   - `python scripts/validate_readiness.py`
