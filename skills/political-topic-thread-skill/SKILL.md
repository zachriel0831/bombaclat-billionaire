---
name: political-topic-thread-skill
description: Design, implement, or review Taiwan politics second-layer topics and political event threads in data-collecting. Use when adding politics topic_id entries, making topic classification category-aware, creating political event thread templates, adding thread_id metadata to topics_json, updating politics classifier tests, or connecting politics articles to public-record evidence.
---

# Political Topic And Thread Skill

## Purpose

Use this skill for Taiwan politics topic classification and event-thread work in
`src/news_platform`.

Stable politics topics are durable product buckets. Event threads are dynamic
overlays for elections, diplomatic visits, policy fights, scandals, budget
cycles, or security incidents.

## Start Here

1. Read `../../spec/political-topic-thread-technical-plan.md`.
2. Read `../../spec/news-topic-classification-functional-spec.md` only when
   changing the existing topic flow.
3. Read `../../spec/news-topic-classification-data-contract.md` when changing
   `topics_json` shape.
4. Use `../../spec/political-event-threads/_template.md` when creating a new
   thread spec.
5. Inspect `../../src/news_platform/topics.py`,
   `../../src/news_platform/topic_classifier.py`, and
   `../../src/news_platform/topic_worker.py` before editing code.

## Rules

- Keep `category` as the source section; do not use it as the issue model.
- Add stable politics buckets as `topic_id`; add short-lived stories as
  `thread_id`.
- Make classifier logic category-aware before adding politics-specific rules.
- Do not create a permanent `topic_id` for a single person, visit, scandal, or
  election cycle.
- Prefer high precision over high recall for politics and public-record links.
- Keep thread metadata additive in `topics_json` until a real normalized table is
  needed by API/frontend query volume.

## Implementation Workflow

1. Decide whether the request is a stable topic change or a dynamic thread.
2. For stable topic changes, update `TopicSpec` rows and classifier tests.
3. For thread changes, copy the template to
   `../../spec/political-event-threads/<thread_id>.md` and fill inclusion,
   exclusion, matching, actor, institution, and verification sections.
4. If runtime thread metadata is needed, add extra fields to the matched
   `topics_json` object; keep existing article category untouched.
5. Update specs or README/PROJECT_INDEX when public behavior changes.

## Verification

Use focused tests first:

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_news_platform_topic_classifier -v
python -m unittest tests.test_news_platform_topic_worker -v
python scripts/validate_readiness.py
```

When a new public-record relation is involved, also run or add focused tests for
`tests.test_news_platform_public_record_matcher`.
