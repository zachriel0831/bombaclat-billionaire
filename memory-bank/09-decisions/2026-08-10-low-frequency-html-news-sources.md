# 2026-08-10 Low-Frequency HTML News Sources

## Decision
Add TVBS, UDN, and SETN as explicit low-frequency `news_platform` HTML list sources for society/politics title collection and reporter enrichment.

## Context
- Existing RSS/sitemap coverage over-represents sources that expose stable feeds.
- TVBS public category pages return usable HTML and JSON-LD article lists, while the old sitemap endpoint is unreliable locally.
- UDN public society/category pages return usable `story-list` article rows. UDN does not expose a pure politics category in the tested navigation, so `6638` is treated as politics-adjacent low-frequency input.
- SETN public `ViewAll.aspx` category pages return usable article rows, but the page also includes all-site breaking news. The parser filters only the main category list and matching visible category label.
- CTEE public pages and sitemap return 403 locally.

## Consequences
- `NEWSPF_DISABLED_SOURCE_IDS` keeps `tvbs,ctee,udn,setn` out of the normal 15-minute loop by default.
- `--source-ids tvbs,udn,setn` explicitly runs the low-frequency sources.
- `scripts/run_news_platform_low_frequency_sources.ps1` performs one controlled crawl, bounded author-detail backfill, and keyword/topic enrichment.
- `scripts/register_news_platform_low_frequency_sources_task.ps1` can register the hourly local schedule.
- CTEE remains disabled until a working allowed public endpoint is verified; do not bypass 403 with rotating user agents, cookies, or proxies.
