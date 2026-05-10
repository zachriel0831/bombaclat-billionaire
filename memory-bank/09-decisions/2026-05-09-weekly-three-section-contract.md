# 2026-05-09 Weekly Three-Section Contract

## Decision
- Weekly summaries use the fixed section contract: `週總經` -> `下週台股配置` -> `下週觀察清單`.
- Weekly summaries are allocation/watchlist briefs, not intraday trade-signal reports.
- Weekly prompt output must connect evidence -> mechanism -> Taiwan implication.

## Rationale
- The previous weekly template reused daily macro-regime section labels and produced shallow prose.
- Weekly delivery needs a clearer Sunday pre-open job: explain the macro regime, translate it into next-week Taiwan allocation, then list concrete watch items.

## Implementation Notes
- `src/event_relay/weekly_summary.py` uses `weekly-summary-three-section-v1`.
- `raw_json.section_contract` records the active headings.
- `raw_json.token_usage` records provider/model/token telemetry for later model quality checks.
