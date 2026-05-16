# News Platform Article To Public Record Matching

- Date: 2026-05-12
- Status: accepted

## Decision
Article-to-public-record linking runs inside `src/news_platform` and writes relations to `t_news_article_public_record_links`.

Matchers are deterministic and high-precision:
- Legislative Yuan legal proposals:
- `matched_by=ly_bill_rule`
- `relation_type=cites` when the bill title appears in article text
- `relation_type=mentions` when the match is based on law/title terms plus supporting evidence
- `evidence_json` records matched law names, title terms, proposer/cosignatory names, article title, record title, and date distance
- NPA 165 fraud-rumor records:
- `matched_by=npa_fraud_rumor_rule`
- `relation_type=mentions`
- `evidence_json` records matched title/title terms, fraud context, article title, record title, dataset URL, and date distance

## Rationale
Public records are structured facts and can support many articles. Matching them in a relation table keeps `t_news_articles` simple while preserving auditable evidence for ranking and explanations.

The first pass intentionally favors precision over recall. Weak matches are skipped instead of writing noisy links.

NPA A1 traffic accident records are stored but not auto-linked yet because date/location-only matching is too noisy for production links.

## Operations
- Manual pass: `python -m news_platform.main --link-public-records`
- Loop mode collects the default public-record source set once per local day, then runs the public-record link pass after crawl, keyword extraction, topic classification, and optional LLM topic fallback.
