# NEWS Requirement Index

This file is the lightweight requirement ledger for the news-platform work in
this repository. It replaces Jira/Notion until a dedicated project-management
system exists.

## ID Rules

- Requirement IDs use `NEWS-<number>`.
- Start at `NEWS-1` and increment by one for each new feature request.
- Create one spec file per requirement: `spec/NEWS-<number>-<short-slug>.md`.
- Do not reuse IDs, even if a requirement is cancelled.
- When a requirement is split, keep the original ID as the parent and create new
  child IDs for implementation-sized follow-ups.

## Status Values

| Status | Meaning |
|---|---|
| `Draft` | Scope is being shaped; implementation should not start unless explicitly approved. |
| `Ready` | Design is stable enough for Codex/sub-agent implementation. |
| `In Progress` | Implementation is active. |
| `Blocked` | Work cannot continue without a decision, dependency, or environment fix. |
| `Done` | Implementation and verification are complete. |
| `Superseded` | Replaced by another NEWS requirement. |

## Requirements

| ID | Status | Title | Spec | Notes |
|---|---|---|---|---|
| `NEWS-1` | `Done` | Reporter identity relations and byline coverage tracking | [NEWS-1-author-coverage-and-reporter-relations.md](NEWS-1-author-coverage-and-reporter-relations.md) | Implemented in data-collecting and exposed through middle-office API endpoints. |
| `NEWS-2` | `Done` | Article detail author backfill | [NEWS-2-article-detail-author-backfill.md](NEWS-2-article-detail-author-backfill.md) | Added conservative detail-page byline extraction and ran first-pass backfill for CNA, Storm, Newtalk, LTN, and ETtoday. |
| `NEWS-3` | `Done` | Second-pass article detail author backfill | [NEWS-3-second-pass-author-backfill.md](NEWS-3-second-pass-author-backfill.md) | Ran second-pass backfill for TVBS, EBC, PTS, and CTEE; EBC remains the primary low-confidence source. |
| `NEWS-4` | `Done` | Free Palestine issue news long-term storage | [NEWS-4-free-palestine-news-long-term-storage.md](NEWS-4-free-palestine-news-long-term-storage.md) | Normalizes `/timeline/news` English issue-news rows into `t_palestine_news_items` and keeps legacy relay rows as backfill input only. |
| `NEWS-5` | `Done` | U.S. macro release calendar reminders | [NEWS-5-us-macro-release-calendar-reminders.md](NEWS-5-us-macro-release-calendar-reminders.md) | Collects official CPI/PPI/nonfarm payrolls/retail sales release dates into `t_macro_release_calendar`; Java sends Taiwan-time day-before reminders. |
| `NEWS-6` | `Done` | Free Palestine news scheduled crawl | [NEWS-6-free-palestine-news-scheduled-crawl.md](NEWS-6-free-palestine-news-scheduled-crawl.md) | Runs `event_relay.palestine_news` every 3 hours into long-term `t_palestine_news_items`. |
| `NEWS-7` | `Done` | Heavyweight earnings calendar reminders | [NEWS-7-heavyweight-earnings-calendar-reminders.md](NEWS-7-heavyweight-earnings-calendar-reminders.md) | Extends `t_macro_release_calendar` with `earnings_<symbol>` rows from Nasdaq / manual overrides; Java groups earnings with macro reminders. |
| `NEWS-8` | `Done` | Finance relay-event reporter enrichment | [NEWS-8-finance-relay-event-reporter-enrichment.md](NEWS-8-finance-relay-event-reporter-enrichment.md) | Enriches short-retention finance RSS rows in `t_relay_events.raw_json` with byline names for frontend display. |
| `NEWS-9` | `In Progress` | Four-hour AI news digest | [NEWS-9-four-hour-ai-news-digest.md](NEWS-9-four-hour-ai-news-digest.md) | Codex automation summarizes finance, society, politics, celebrity, and Free Palestine context into Redis for API reads. |

## Next ID

The next requirement ID is `NEWS-10`.
