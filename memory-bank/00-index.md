# Memory Bank Index

For whole-repo navigation, start at [../PROJECT_INDEX.md](../PROJECT_INDEX.md). This file indexes only the memory-bank and nearby task/review material.

## Active Core
- `memory-bank/PROJECT_DOCUMENTATION.md`: project overview, architecture, source contracts
- `memory-bank/rules.md`: development, security, and quality rules
- `memory-bank/workflows.md`: operational workflows and runbooks
- `memory-bank/restart-recovery-runbook.md`: machine-restart recovery steps and post-restart checks
- `memory-bank/rag-operations.md`: RAG indexing, retrieval, config, telemetry, and verification

Do not read every file by default. Load only the file needed for the current task.

## Task Management
- `tasks/todo.md`: plan/progress/verification checklist for active work
- `tasks/lessons.md`: append-only correction lessons with prevention rules

## Reviews
- `memory-bank/pr-review.md`: PR template and review output format
- `memory-bank/20-pr-review-standards.md`: detailed review checklist

## Decisions
- `memory-bank/09-decisions/`: architecture and process decisions
- `memory-bank/09-decisions/2026-04-30-market-calendar-guard.md`: daily analysis holiday routing decision
- `memory-bank/09-decisions/2026-05-05-structural-market-context-modules.md`: structural market-context module decision
- `memory-bank/09-decisions/2026-05-05-scorecard-context-pack.md`: deterministic scorecard and prompt context-pack decision
- `memory-bank/09-decisions/2026-05-07-hybrid-rag-stage0-claim-router.md`: hybrid RAG, stage0 thesis selector, claim verifier, and quota-aware model-routing decision
- `memory-bank/09-decisions/2026-05-09-visible-us-close-recommendations.md`: deterministic visible fixed-pool watch section for delivery-eligible U.S. close analyses
- `memory-bank/09-decisions/2026-05-11-fixed-market-analysis-watch-pool.md`: fixed five-stock market_analysis watch pool; no model-selected Taiwan ticker recommendations
- `memory-bank/09-decisions/2026-05-09-weekly-three-section-contract.md`: weekly output contract for `週總經` / `下週台股配置` / `下週觀察清單`
- `memory-bank/09-decisions/2026-05-11-news-platform-topic-classification.md`: MVP topic classification storage on `t_news_articles.topics_json`
- `memory-bank/09-decisions/2026-05-11-news-platform-llm-topic-fallback.md`: OpenAI-first optional LLM fallback for category-specific general news topic rows
- `memory-bank/09-decisions/2026-05-11-news-platform-politics-crawler.md`: Taiwan politics crawler category and category-specific general fallback topic
- `memory-bank/09-decisions/2026-05-11-news-platform-public-record-links.md`: structured official public records and article-record link table
- `memory-bank/09-decisions/2026-05-11-news-platform-ly-bills-public-record-source.md`: Legislative Yuan bill API stored as public records
- `memory-bank/09-decisions/2026-05-11-taiwan-finance-rss-relay-events.md`: Taiwan finance RSS feeds write to `t_relay_events`
- `memory-bank/09-decisions/2026-05-12-news-platform-public-record-matching.md`: deterministic article-to-public-record matching
- `memory-bank/09-decisions/2026-05-12-four-track-source-expansion.md`: four-track Taiwan source expansion across article, relay RSS, official finance/macro, and public-record paths
- `memory-bank/09-decisions/2026-05-14-healthcare-public-record-sources.md`: healthcare public-record sources and `healthcare_burden` mapping
- `memory-bank/09-decisions/2026-05-14-justice-corrections-public-record-sources.md`: justice/corrections public-record sources and judicial burden mapping
- `memory-bank/09-decisions/2026-05-14-politics-l2-topic-thread-model.md`: stable politics second-layer topic IDs and dynamic event-thread model
- `memory-bank/09-decisions/2026-05-15-news-article-author-metadata.md`: article reporter/author metadata on `t_news_articles.authors_json`
- `memory-bank/09-decisions/2026-05-15-news-author-relations-and-coverage.md`: normalized author relations and byline coverage metrics

## Archived / On Demand
- `memory-bank/archive/enterprise/40-agent-enterprise-readiness.md`: enterprise baseline for production agents
- `memory-bank/archive/enterprise/41-skills-engineering-standard.md`: skill lifecycle and quality standard
- `memory-bank/archive/enterprise/42-agent-evals-and-release-gates.md`: eval framework and release gates
- `memory-bank/archive/enterprise/43-agent-security-and-compliance.md`: security controls and compliance checklist
- `memory-bank/archive/enterprise/44-mcp-server-governance.md`: MCP onboarding and governance rules
