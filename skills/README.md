# Skills Workspace

This folder is the canonical location for skill assets in this repository.

## Structure
- `skills/registry.yaml`: global skill registry and ownership
- `skills/templates/`: templates for new skills
- `skills/<skill-name>/`: concrete skill implementation docs and assets
- `skills/macro-weekly-summary-skill/` and `skills/line-brief-format-skill/`: prompt assets consumed by analysis jobs; they are not registered enterprise skills and do not own delivery behavior

## Required files per skill
Registered enterprise skills must include:
- `SKILL.md`
- `EVALS.md`
- `CHANGELOG.md`

## Quick start
1. Copy templates from `skills/templates/`.
2. Register the skill in `skills/registry.yaml`.
3. Fill required fields and owners.
4. Add eval cases and thresholds.
5. Run readiness validation script:
   - `python scripts/validate_readiness.py`
