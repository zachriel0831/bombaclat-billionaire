# Decision: News Platform Topic Classification Storage

## Context
The Taiwan society/politics news platform needs issue classification as the base layer for later timelines, emotion aggregation, media-behavior observation, and stance recommendations.

## Decision
For the MVP, topic classification is stored on the existing `t_news_articles` table in `topics_json` plus row-level classification metadata.

The worker flow is:
1. crawler writes article rows
2. `KeywordWorker` fills `keywords_json`
3. `TopicWorker` reads rows with `topics_json IS NULL AND keywords_json IS NOT NULL`
4. deterministic rules write up to three specific topic hits to `topics_json`; no-hit rows become category-specific general topics (`general_social_news` / 一般社會新聞 or `general_politics_news` / 一般政治新聞)
5. optional LLM fallback reads rule fallback rows and writes one LLM topic or keeps the category-specific general topic

`topic_classified_by` prevents repeat-spend loops:
- `rule`: deterministic classifier has run
- `llm`: LLM fallback has run

`topics_json[0].topic_id IN ('general_social_news','general_politics_news') AND topic_classified_by='llm'` means both layers processed the article but no specific topic matched.

## Rationale
- Matches the existing `keywords_json` backfill pattern.
- Keeps the first release small and easy to migrate.
- Preserves per-article classification snapshots for later retuning or audits.
- Keeps the LLM fallback optional and bounded to rule fallback rows only.

## Deferred
A normalized `t_news_article_topics` relation table is deferred until timeline/query workloads require faster filtering, aggregation, or richer per-topic metadata.
