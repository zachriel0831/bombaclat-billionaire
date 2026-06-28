# Prior Signal Reference Fallback

## Date
2026-05-18

## Status
Historical fallback rule. Superseded for trading-candidate policy on 2026-06-02 by `2026-06-02-dynamic-intraday-candidate-pipeline.md`.

## Decision
When a delivery-visible `pre_tw_open` or eligible `us_close` analysis lacks a current fixed-pool row for one of the ten monitored Taiwan tickers, the pipeline may copy the most recent same-ticker row from `t_trade_signals` into the current analysis as `prior_signal_stock_watch`.

## Boundaries
- Use prior rows only for the same ticker in the fixed ten-stock pool.
- Copy only reference levels and rationale: entry, stop, target, holding horizon, and notes.
- Downgrade to `confidence=low`.
- Label the rationale as prior reference and require same-day price, volume, and news confirmation.
- Do not use prior rows to add non-pool tickers or to claim a fresh buy signal.

## Reason
The visible fixed-pool section should avoid empty repeated "no valuation / no condition" rows when the local database already has recent same-ticker reference levels. The fallback improves continuity while preserving the evidence boundary that stale conditions are not current confirmation.

Do not use this fallback to justify current dynamic Taiwan intraday / short-swing candidates. Dynamic candidates require current relay-event, market-context, quote, and model evidence.
