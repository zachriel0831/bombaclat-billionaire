# 2026-05-14 - Politics second-layer topics and event threads

## Context

Taiwan politics articles are already collected as `category=politics`, but most
runtime topic rules are social/policy issues. Political stories often persist
for months or years, and one-off events such as a diplomatic visit or an election
cycle should not become permanent topic IDs.

## Decision

Define a small stable second-layer politics topic catalog and use dynamic
`thread_id` overlays for specific events.

Initial stable politics topics:

- `elections`
- `cross_strait_relations`
- `foreign_affairs`
- `legislative_policy`
- `party_politics`
- `political_accountability`
- `defense_security`
- `public_budget`

Event threads are documented with `spec/political-event-threads/_template.md`
and can be stored as additive metadata inside `topics_json` during the MVP.

## Consequences

- The classifier is category-aware through `TopicSpec.categories`; the initial
  politics rules only run for rows whose article category normalizes to
  `politics`.
- `category=politics` remains a source section, not the topic model.
- Short-lived stories such as leader visits, election cycles, and scandals use
  `thread_id`, not new permanent `topic_id` values.
- Normalized thread tables are deferred until API/frontend query volume requires
  them.
