# Decision: Add Taiwan Politics News Category

## Context
The news platform already collects Taiwan society news and stores category on `t_news_articles`. The next crawler scope is Taiwan politics news, and it should reuse the same article, keyword, topic, and optional LLM fallback flow.

## Decision
Add `politics` as a first-class `news_platform` category while keeping the existing table design.

The source registry now supports:
- `society`
- `politics`

Default CLI behavior crawls `society,politics`; operators can limit scope with `--categories` or `NEWSPF_CATEGORIES`.

Politics source mapping:
- LTN politics RSS
- ETtoday politics HTML list (`category id=1`) parsed by `EttodayNewsListSource`
- TVBS Google News sitemap filtered by `/politics/`
- CNA politics RSS
- EBC realtime sitemap filtered by `/news/politics/`

## Fallback Topics
Rule/LLM no-hit rows remain visible with category-specific general topics:
- `society` → `general_social_news`
- `politics` → `general_politics_news`

## Rationale
- Reuses `t_news_articles.category`, so no schema migration is needed.
- Keeps crawler adapters isolated by source kind.
- Avoids using ETtoday all-news RSS for politics, because the feed is mixed and not category-safe.
- Keeps the ETtoday TLS verification workaround scoped to its public category-list source, because the site certificate fails Python's strict SKI check on this Windows/OpenSSL build.
- Keeps frontend and middle-office contracts simple: `category` is the source section, `topics_json[0]` is the primary issue label.
