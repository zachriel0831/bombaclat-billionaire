# Decision: Normalize news authors and track byline coverage

Date: 2026-05-15

## Context

`t_news_articles.authors_json` already stores reporter/author names when RSS,
sitemap, or high-confidence byline extraction provides them. The platform now
needs reporter-level analysis and source-level transparency metrics, including
articles where no reporter name is available.

## Decision

- Keep `authors_json` as the raw article-level compatibility field.
- Add `t_news_authors` for normalized source-scoped reporter identities.
- Add `t_news_article_authors` for article-to-author relations.
- Add article-level author extraction status fields on `t_news_articles`.
- Add `t_news_author_coverage_daily` for materialized daily source/category
  byline coverage.
- Do not create fake `unknown` author rows. Missing reporter names are counted
  through article status and coverage metrics.

## Consequences

- Middle-office tooling can query reporters, reporter-article links, and source
  coverage without changing public frontend article cards.
- Coverage can separate crawler/parser limitations from possible source byline
  non-disclosure.
- Existing rows require periodic backfill/coverage scripts until the pipeline
  fully refreshes historical rows.
