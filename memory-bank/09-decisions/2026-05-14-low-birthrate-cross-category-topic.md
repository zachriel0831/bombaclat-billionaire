# 2026-05-14 Low Birthrate Cross-Category Topic

## Status
Accepted

## Context
The user-facing 少子化 page was opened under the society route and showed 0 articles even though current matching articles existed under politics and other source categories. Keeping the page strictly category-scoped made issue tracking look broken.

## Decision
Treat `low_birthrate` as a cross-category issue view in the middle-office API. For single-topic requests with `topic=low_birthrate`, topic counts, article lists, and timelines aggregate matching rows from all `t_news_articles.category` values. Returned article rows preserve their original `category`.

Other topics remain scoped to the route category.

## Verification
- API regression test covers society-route topic count, article list, and timeline aggregation for `low_birthrate`.
