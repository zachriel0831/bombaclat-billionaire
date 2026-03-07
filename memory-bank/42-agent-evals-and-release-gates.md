# Agent Evaluation and Release Gates

## 1. Evaluation Layers
- Unit evals:
  - parser correctness
  - schema validation
  - deterministic business logic
- Workflow evals:
  - tool selection correctness
  - multi-step completion quality
- Safety evals:
  - prompt injection resilience
  - data exfiltration prevention
  - policy refusal behavior
- Regression evals:
  - previously fixed incidents
  - lessons-driven test cases

## 2. Core Metrics
- Task success rate
- Tool-call precision / invalid tool-call rate
- Hallucinated tool-call rate
- Policy violation rate
- Latency p50/p95
- Error budget burn

## 3. Release Criteria
Release is blocked if any condition fails:
- No baseline-to-candidate eval comparison
- Quality metrics below threshold
- Safety evals missing or failing
- Rollback path untested
- Observability dashboards/alerts missing

## 4. Online Validation
- Shadow mode before full traffic.
- Progressive rollout (small percentage to full rollout).
- Auto-rollback triggers:
  - sustained spike in invalid tool calls
  - safety violations above threshold
  - SLO breach

## 5. Required Release Evidence
- Eval report with metric deltas
- Known-risk list
- Rollback command/runbook
- Approval sign-off from product + engineering + security

## References
- OpenAI evaluation best practices: https://platform.openai.com/docs/guides/evals
- OpenAI agents best practices: https://developers.openai.com/cookbook/examples/agents_sdk/multi-agent-portfolio-collaboration/multi_agent_portfolio_collaboration/
- NIST AI RMF Playbook: https://airc.nist.gov/AI_RMF_Knowledge_Base/Playbook
