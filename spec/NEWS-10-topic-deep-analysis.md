# NEWS-10 Topic Deep Analysis Articles

## Status

Ready

## Context

Topic pages should have a `深度分析` tab that explains why a Taiwan issue exists,
how serious it is, and what comparable countries show. The first version can be
model-generated, but the data model must leave room for future reader and
columnist submissions.

## Requirement

Store professional topic-level analysis articles separately from news cards and
short-lived discussion messages.

The first article type is `root_cause`: a data-backed long-form analysis for one
`category + topic_id`, for example `society + drunk_driving_accident`.

## Product Contract

Each analysis article should include:

- clear thesis and executive summary
- Taiwan problem structure and root causes
- Taiwan trend / scale evidence from existing platform data or public records
- international comparisons with source attribution
- stakeholders and incentive conflicts
- policy options with tradeoffs
- data gaps and confidence limits

The tone should read like a professional public-affairs column, not a raw model
report. Internal field names such as `scorecard`, `context_pack`, or pipeline
stage labels must not be shown to users.

`body_markdown` must be long-form enough to stand alone as an analysis article:
target 1,200 to 2,000 Chinese characters for the MVP root-cause article. Use
plain Markdown with a blank line after every heading, for example
`## 一句話\n\n...`, so frontend renderers do not merge section titles and body
copy into one oversized heading.

## Non-Goals

- No full CMS or rich editor in this step.
- No separate contributor identity system in this step.
- No permanent analysis content in Redis.
- No rewrite of the existing public comments tables.

## Data Contract

Primary table: `t_topic_deep_analyses`

Purpose: one row per generated or submitted analysis article.

Important fields:

- `category`, `topic_id`, `analysis_type`: topic identity.
- `title`, `summary`, `body_markdown`: article content.
- `root_causes_json`, `taiwan_data_json`, `international_comparisons_json`,
  `policy_options_json`, `limitations_json`: structured evidence for future UI
  widgets and audits.
- `status`: `draft`, `submitted`, `reviewing`, `published`, `rejected`, or
  `archived`.
- `origin`: `model_generated`, `staff_editorial`, `reader_submission`, or
  `columnist_submission`.
- `author_type`, `author_user_id`, `author_display_name`: supports current model
  authorship and future logged-in contributors.
- `model_name`, `prompt_version`, `generation_run_id`: model generation audit.
- `source_window_start`, `source_window_end`, `source_count`: analysis input
  window.

Source table: `t_topic_deep_analysis_sources`

Purpose: citations, dataset facts, public-record links, and international
comparison evidence.

Supported source classes:

- `news_article`
- `public_record`
- `dataset`
- `external_url`
- `manual_note`

Source roles:

- `primary_data`
- `news_context`
- `international_comparison`
- `policy_reference`
- `counterpoint`
- `limitation`

## Future Submission Design

Reader or columnist posts use the same `t_topic_deep_analyses` table:

- create with `origin=reader_submission` or `columnist_submission`
- set `status=submitted`
- link `author_user_id` to future `t_public_users.id` when login exists
- keep `author_display_name` as a snapshot for display

This avoids a second draft table until moderation volume proves it is needed.

## Discussion Design

Topic-level chat/barrage remains owned by the topic surface.

Analysis-article comments can reuse the existing public comments model later:

- `t_public_comment_threads.target_type = 'topic_deep_analysis'`
- `t_public_comment_threads.target_id = t_topic_deep_analyses.id`
- `t_public_comments.target_type = 'topic_deep_analysis'`

No extra comment table is required for this requirement.

## Planned API Contract

Read latest published article:

```text
GET /api/{category}/topics/{topicId}/deep-analysis?type=root_cause
```

Expected query:

```sql
SELECT *
FROM t_topic_deep_analyses
WHERE category = ?
  AND topic_id = ?
  AND analysis_type = 'root_cause'
  AND status = 'published'
ORDER BY published_at DESC, id DESC
LIMIT 1;
```

Return the article plus ordered rows from `t_topic_deep_analysis_sources`.

Admin/editor writes should be protected by the existing admin-auth/rate-limit
work before they are exposed.

## Generation Input

The model generation job should use compact context only:

- recent topic articles from `news_platform.t_news_articles`
- linked public records from `t_public_records`
- topic timelines / media behavior summaries already computed in the platform
- official Taiwan statistics where available
- selected international indicators from official, NGO, or academic sources

The job should write a `draft` row first. Human or guard automation can promote
it to `published` after checking readability, source coverage, and no mojibake.

## DoD

- SQL migration exists for the two tables.
- First model-generated article can be stored as `draft` or `published`.
- Sources can represent Taiwan data and international comparison evidence.
- Future reader/columnist submissions do not require a schema rewrite.
- API can fetch the latest published article by `category + topic_id`.
