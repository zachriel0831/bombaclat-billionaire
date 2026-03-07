# Agent Security and Compliance Controls

## Threat Categories (Minimum)
- Prompt injection and instruction override
- Sensitive data leakage
- Insecure tool invocation
- Excessive agent autonomy without guardrails
- Supply chain risk from dependencies and tools

## Baseline Controls
1. Identity and access
- service-level authn/authz
- least privilege for tool credentials

2. Input/output controls
- strict schema validation for tool arguments
- output filtering and policy checks before user delivery

3. Secret management
- no hardcoded keys
- managed secret store or CI secret manager
- key rotation policy

4. Runtime protections
- per-tool timeouts
- retry limits and circuit breakers
- sandboxing for untrusted execution

5. Audit and traceability
- request IDs and trace IDs
- immutable audit trail for high-risk actions

6. Incident handling
- severity model and on-call escalation
- containment, recovery, and postmortem loop

## Compliance Readiness Checklist
- Data classification matrix exists.
- Retention and deletion policy exists.
- Cross-border data handling policy exists when applicable.
- Human oversight path exists for high-impact decisions.
- Audit logs are retained for required duration.

## References
- OWASP LLM Top 10: https://owasp.org/www-project-top-10-for-large-language-model-applications/
- MITRE ATLAS: https://atlas.mitre.org/
- NIST SSDF: https://csrc.nist.gov/projects/ssdf
- EU AI Act overview: https://artificialintelligenceact.eu/
