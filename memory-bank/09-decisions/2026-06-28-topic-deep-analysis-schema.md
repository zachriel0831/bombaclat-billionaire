# Topic Deep Analysis Schema

Date: 2026-06-28

## Decision

Store per-topic professional analysis articles in `t_topic_deep_analyses`, with
citations and international comparison evidence in
`t_topic_deep_analysis_sources`.

## Rationale

- Topic analyses are long-lived editorial/reference content, not transient news
  rows and not barrage messages.
- A single content table is enough for model-generated articles, staff edits,
  future reader submissions, and columnist submissions.
- Sources stay normalized so Taiwan facts, official records, and international
  comparisons can be audited and rendered separately later.
- Existing public comments can attach to analysis rows with
  `target_type='topic_deep_analysis'`; no new comment table is needed.

## Deferred

- Full CMS/editor workflow.
- Dedicated contributor profile table.
- Revision history table.
- Automated source-quality scoring.
