# EVALS: political-topic-thread-skill

## Eval Scope

- Correctly distinguish stable politics `topic_id` work from dynamic
  `thread_id` work.
- Preserve `category` as the source section.
- Require category-aware classifier logic before politics rules are added.
- Add targeted regression tests for false positives.

## Offline Cases

| Case ID | Scenario | Expected Result | Category |
|---|---|---|---|
| POL-001 | Add `elections` topic rules for campaign and polling articles. | Agent updates topic specs and classifier tests without changing source ingestion. | happy-path |
| POL-002 | Add a one-off "Trump China visit" tracker. | Agent creates a thread spec under `spec/political-event-threads/` instead of a permanent topic. | happy-path |
| POL-003 | A society article mentions a company board election. | Agent adds category-scope or exclude rules so it does not classify as politics `elections`. | edge-case |
| POL-004 | User asks to add normalized thread tables immediately. | Agent checks API/frontend need first and recommends `topics_json` additive MVP unless query volume justifies schema. | governance |

## Pass/Fail Gates

- Must keep topic IDs lowercase snake_case.
- Must include at least one positive and one negative test per new stable topic.
- Must run `python scripts/validate_readiness.py`.
