# Archived Task - 2026-05-11 PTS source

## Outcome
Added PTS/Public Television as a Taiwan society/politics news crawler source.

## Evidence
- `python -m unittest tests.test_news_platform_registry tests.test_news_platform_pts_category tests.test_news_platform_main` passed 9 tests.
- Politics smoke found `pts:politics` 15 items.
- Society smoke found `pts:society` 15 items.
- Restarted live loop showed `pts:society` 15, `pts:politics` 15, `fetched=218`, `failed=0`.

## Open Risks
PTS category pages are HTML, so markup changes can break parsing; smoke test covers current live shape.
