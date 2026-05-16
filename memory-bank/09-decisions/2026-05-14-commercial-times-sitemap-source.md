# 2026-05-14 Commercial Times Sitemap Source

## Decision
- Add Commercial Times (`ctee` / 工商時報) as a normal Taiwan society/politics news source through its public Google News sitemap.
- Use source-category filtering only:
  - `-431401` -> `society` (`articleSection=生活`)
  - `-430104` -> `politics` (`articleSection=要聞`)
- Do not hard-code any issue relation such as `low_birthrate`; existing keyword/topic workers classify articles normally after ingestion.

## Context
- `ctee.com.tw/feed` and common RSS paths return 403.
- `https://www.ctee.com.tw/robots.txt` advertises `https://www.ctee.com.tw/sitemaps/sitemap_newstoday.xml`.
- Existing `GoogleNewsSitemapSource` can parse the sitemap and preserve source timestamps.

## Verification
- `ctee:society` smoke fetch returned current `-431401` articles.
- `ctee:politics` smoke fetch returned current `-430104` articles.
