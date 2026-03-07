# Enterprise Agent Readiness Baseline

This document defines the minimum baseline for building and operating production AI agents in a mature team.

## 1. Strategy and Scope
- Define business outcomes, non-goals, and risk appetite.
- Define agent boundaries:
  - user intents in scope
  - explicit out-of-scope behavior
  - escalation to human or fallback path
- Define service-level objectives (SLOs):
  - latency target
  - reliability target
  - quality target (task success rate)

## 2. Operating Model
- Required owners:
  - Product owner (use-case and policy decisions)
  - Engineering owner (runtime and release)
  - Security owner (threat model and controls)
  - Evaluation owner (quality gates and drift monitoring)
- Required ceremonies:
  - weekly eval review
  - incident retrospective
  - monthly control review (security/compliance)

## 3. Architecture Baseline
- Agent orchestration pattern documented (single-agent first, multi-agent only if evals justify it).
- Tool contracts defined with explicit schemas and failure semantics.
- Prompt and policy versioning with rollback capability.
- Idempotent execution design for retries.
- Structured telemetry for every agent step.

## 4. Required Artifacts
- Product spec and acceptance criteria
- Threat model and misuse cases
- Evaluation suite and baseline scores
- Release checklist and rollback runbook
- Incident response runbook
- Data retention and deletion policy

## 5. Production Gates (Must Pass)
- Security gate: secrets, authz, input/output controls
- Reliability gate: retry, timeout, circuit breaker, graceful degradation
- Quality gate: offline and online eval thresholds
- Observability gate: traceability and alerting coverage
- Compliance gate: data handling and auditability requirements

## 6. Continuous Improvement
- Track regressions by category:
  - hallucinated tool calls
  - policy violations
  - runtime failures
  - degraded user outcomes
- Use correction loops:
  - update `tasks/lessons.md`
  - convert repeated issues into enforceable rules and CI checks

## Sources
- NIST AI RMF: https://www.nist.gov/itl/ai-risk-management-framework
- NIST AI RMF GenAI Profile: https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- OWASP LLM Top 10: https://owasp.org/www-project-top-10-for-large-language-model-applications/
- ISO/IEC 42001:2023: https://www.iso.org/standard/81230.html
