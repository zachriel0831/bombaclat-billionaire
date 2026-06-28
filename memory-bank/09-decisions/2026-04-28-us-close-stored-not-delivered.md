# 2026-04-28 - US Close Stored, Not Delivered

## Decision
- `us_close` market analysis remains generated and stored in `t_market_analyses`.
- Superseded on 2026-05-01: `us_close.push_enabled` is `1` only when TW is closed and the relevant U.S. close session was open.
- `us_close` is upstream context for the next Taiwan `pre_tw_open` analysis only when that U.S. session was open.

## Rationale
- The user-facing LINE message should focus on Taiwan pre-open.
- U.S. close facts are still valuable evidence for Taiwan morning analysis.
- `push_enabled` means Java delivery eligibility, not Python push execution.

## Current Policy
- `pre_tw_open`: `push_enabled=1`
- `us_close`: `push_enabled=1` only when TW closed + relevant U.S. close session open; otherwise `0`
- `macro_daily`: `push_enabled=1`
- `tw_close`: `push_enabled=0`

## 2026-04-28 Follow-up
- Taiwan `pre_tw_open` prompts include the latest stored `us_close` row only when the relevant U.S. session was open.
- `pre_tw_open` uses a larger 700-1300 Chinese-character budget so U.S. close facts and Taiwan watch rows can both fit.
- Amended 2026-05-16: visible stock rows use the current ten-stock fixed pool from `2026-05-16-ten-stock-observation-template.md`; TWSE/Yahoo context fills evidence for those symbols only and must not top up with substitute tickers.
- Fixed-pool watch lines are appended under `## 今日個股觀察`; they remain signals/watch items, not orders.
