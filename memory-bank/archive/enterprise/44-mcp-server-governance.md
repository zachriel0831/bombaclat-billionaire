# MCP Server Governance

## Purpose
Define how MCP servers are approved, configured, and monitored in enterprise environments.

## Onboarding Checklist
- Business justification and owner
- Data classification impact
- Permission scope review (read/write/network/system)
- Secret requirements and storage location
- Failure behavior and fallback path
- Logging and audit requirements

## Required Metadata Per Server
- `name`
- `owner`
- `purpose`
- `allowed_operations`
- `required_env_vars`
- `data_access_level`
- `runbook_url`

## Configuration Rules
- Prefer explicit allowlists over broad access.
- Keep server permissions minimal.
- Separate dev and prod configurations.
- Keep example config in repo, real secrets outside repo.

## Operational Rules
- Monitor error rates and latency per server.
- Track top tools used and failure patterns.
- Disable or quarantine misbehaving servers quickly.
- Review permissions quarterly.

## Security Rules
- No token in plaintext config files committed to git.
- Validate external server trust and update cadence.
- Pin versions for high-risk servers where possible.

## References
- MCP specification: https://modelcontextprotocol.io/specification/2025-06-18
- OpenAI agentic governance cookbook: https://developers.openai.com/cookbook/examples/partners/agentic_governance_guide/agentic_governance_cookbook/
