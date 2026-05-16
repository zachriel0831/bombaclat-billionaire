# Political Event Thread Template

Copy this file to `spec/political-event-threads/<thread_id>.md`.

Use a thread when a political story is narrower than a stable `topic_id` and
needs its own timeline, actors, media-behavior view, or public-record matching.

```yaml
thread_id: example_thread_2026
thread_label: 範例政治事件
status: candidate
topic_id: foreign_affairs
event_type: diplomatic_visit
time_scope:
  starts_at: 2026-01-01
  ends_at:
geo_scope:
  - TW
  - US
actors:
  people:
    - Donald Trump
  parties: []
  governments:
    - Taiwan
    - United States
institutions:
  - MOFA
  - White House
keywords:
  primary:
    - 川普訪中
    - Trump China visit
  supporting:
    - 台美
    - 美中
    - 外交部
  exclude:
    - 旅遊
official_records:
  expected_sources:
    - ly_bills
  matching_notes: Link only when a bill, official statement, or public record explicitly relates to this event.
acceptance_tests:
  positive_titles:
    - 川普訪中牽動台美中關係 外交部回應
  negative_titles:
    - 旅遊業者推川普主題中國行程
```

## Required Sections

### Product Reason

Explain why this event should be a thread instead of just a normal article under
the stable topic. Mention the user-facing value: timeline, actor tracking,
media behavior, official-record context, or election-cycle tracking.

### Inclusion Rules

List what should be included. Be specific about actors, institutions, timeframe,
and issue boundary.

### Exclusion Rules

List common false positives. Include same names used in non-political contexts,
tourism/culture articles, historical retrospectives, or unrelated party attack
articles.

### Matching Strategy

State whether the first implementation should be rule-only, LLM-assisted, or
manual-review-only. Prefer high precision.

### Verification Notes

Include the exact classifier tests or smoke checks a sub-agent should add.
