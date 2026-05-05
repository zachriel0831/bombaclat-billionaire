# Market Calendar Guard

Date: 2026-04-30

## Decision
Daily market analysis must check a built-in TWSE / NYSE market calendar before calling the LLM.

## Rules
- Sunday: daily market analysis skips; weekly summary owns the day.
- TW closed + relevant U.S. close session open: only `us_close` runs.
- Relevant U.S. close session closed + TW open: only `pre_tw_open` / `tw_close` run; stale `us_close` context is not injected into the model prompt.
- TW and relevant U.S. close session both closed: the `pre_tw_open` task writes `macro_daily` with `push_enabled=1`.

## Notes
- The U.S. close session date is Taiwan local date minus one day.
- `macro_daily` writes to `t_market_analyses`, is Java-delivery eligible, and does not create trade signals.
- Built-in holiday lists currently cover 2026 and should be refreshed before future years are relied on.
