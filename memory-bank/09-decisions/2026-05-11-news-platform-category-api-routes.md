# News Platform Category API Routes

## Decision
Use category-specific middle-office routes for Taiwan tracked news:

- `GET /api/society/topics`
- `GET /api/society/articles`
- `GET /api/society/articles/{id}`
- `GET /api/politics/topics`
- `GET /api/politics/articles`
- `GET /api/politics/articles/{id}`

The route category maps directly to `t_news_articles.category`.

## Rationale
The collector stores society and politics rows in the same `t_news_articles` table, with `category` as the boundary and `topics_json` as the MVP topic snapshot. Category-specific routes keep frontend navigation simple while avoiding a new article-topic relation table before timeline/query volume requires it.

## Consequences
- Society fallback topic remains `general_social_news`.
- Politics fallback topic is `general_politics_news`.
- Frontend topic pages call the category route and pass `topic=<topicId>`.
- Normal UI should use `topics`, `primaryTopic`, and `topicClassificationStatus` from the API response instead of parsing `topics_json`.
