# Skills Engineering Standard

This standard defines how to design, build, test, release, and deprecate skills.

## Skill Definition of Done
A skill is production-ready only when all items below are complete:
- Problem statement and intended users are explicit.
- Input/output contract is explicit.
- Tool dependencies and permissions are documented.
- Failure modes and fallback behavior are documented.
- Eval cases exist (happy path, edge cases, adversarial cases).
- Version and changelog are updated.

## Skill File Structure
For each skill directory:
- `SKILL.md`: usage contract and operational guidance
- `EVALS.md`: scenario list and pass criteria
- `CHANGELOG.md`: versioned change log

## SKILL.md Required Sections
- Purpose
- Trigger rules
- Inputs required
- Outputs and format
- Tools and permissions
- Failure handling
- Safety and compliance notes
- Verification steps

## Development Workflow
1. Draft contract and constraints.
2. Implement smallest viable version.
3. Add eval scenarios and expected outputs.
4. Run local validation and record evidence.
5. Release with version bump and changelog note.

## Versioning Rules
- Use semantic versioning:
  - MAJOR: breaking contract changes
  - MINOR: backward-compatible behavior additions
  - PATCH: bug fixes without contract changes
- Every release must add changelog notes.

## Deprecation Rules
- Mark deprecated skills with sunset date and replacement.
- Keep compatibility shim period when possible.
- Remove only after migration and sign-off.

## References
- Model Context Protocol: https://modelcontextprotocol.io/specification/2025-06-18
- OpenAI eval guidance: https://platform.openai.com/docs/guides/evals
- OpenAI guardrails cookbook resource page: https://developers.openai.com/cookbook/examples/partners/agentic_governance_guide/agentic_governance_cookbook/
