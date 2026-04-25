# Decision: Market Quote Snapshots and Significant-Move Events

## Date
2026-04-25

## Context
REQ-019 introduces price/volume monitoring for the auto-trading path.
Per the boundaries doc (`2026-04-25-auto-trading-system-boundaries.md`), high-
frequency quote rows must NOT bloat `t_relay_events`. Source data goes to a
dedicated snapshot table; only standardised significant moves become events.

Pre-existing `scrapers/yfinance_stocks.py` was pushing every quote into
`t_relay_events` via `/events`, which violates that rule.

## Decision

### Two-table split
- **`t_market_quote_snapshots`** (new) — every poll writes one row per symbol.
  Columns: symbol, market, session, ts, open/high/low/close, prev_close,
  volume, turnover, change_pct, source, raw_json. Unique key
  `(symbol, ts, source)`.
- **`t_relay_events`** — only standardised move events with
  `source=market_quote:<market>` and `raw_json.dimension="market_quote"`. One
  event per (symbol, trade_date, event_type) so re-runs don't duplicate.

### Detection (pure-functional, `event_relay.quote_movement`)
Default thresholds:
- `gap_up` / `gap_down` — `|open − prev_close| / prev_close >= 1%`
- `sharp_up` / `sharp_down` — `|change_pct| >= 3%`
- `volume_spike` — `volume >= 2x n_day_avg_volume` (window default 20 bars,
  whatever the caller supplies)

All thresholds overrideable via `MovementThresholds`. Stable event_id format:
`market-quote-{market}-{symbol}-{trade_date}-{event_type}`.

### Source mapping (yfinance → market)
| WATCHLIST category | market label | example symbols |
|---|---|---|
| `taiwan` | TW | 2330.TW, 2317.TW |
| `us` | US | AAPL, NVDA |
| `index` | INDEX | ^TWII, ^GSPC, ^IXIC, ^DJI |
| `crypto` | CRYPTO | BTC-USD, ETH-USD |
| `macro` | MACRO | ^VIX, ^TNX, NKD=F |
| `forex_commodity` | FX | TWD=X, CL=F, GC=F |

Snapshot row carries `source = "yfinance:<category>"` so the original feed is
recoverable; the move event uses `source = "market_quote:<market>"` per the
event contract.

### Polling cadence (current scaffolding; tune per market in REQ-024)
| Slot | Cadence | Trigger |
|---|---|---|
| pre-market scan | 1× / day at TW pre-open and US pre-open | scheduled task |
| intraday TW | every 5 min, 09:00–13:30 Asia/Taipei (trading days) | scheduled task |
| intraday US | every 5 min, 09:30–16:00 ET (trading days) | scheduled task |
| close summary | 1× post-close per market | scheduled task |

The yfinance scraper is the v1 implementation. Real-time intraday cadence is
deferred to REQ-024 (watchlist monitoring) — yfinance daily granularity is
fine for the snapshot/move pipeline at this stage.

### HTTP contract
- `POST /quote-snapshots` — JSON array of snapshot rows; relay coerces and
  upserts into `t_market_quote_snapshots`.
- `POST /events` — only the move events emitted by
  `quote_movement.detect_movement_events`.

## Consequences
- `t_relay_events` no longer fills with one row per symbol per poll. Analysis
  prompts that scan recent events will see real signal density, not noise.
- REQ-024 watchlist can read `t_market_quote_snapshots` for price/volume
  refreshes without parsing event titles.
- A polling run with no significant moves emits zero events — verify
  separately via the snapshot table that the run actually happened.
- Detection thresholds are intentionally generic; per-symbol tuning belongs
  in `t_strategy_symbol_overrides` (REQ-025).

## Alternatives considered
- **Detect server-side on snapshot ingestion.** Cleaner, but requires the
  server to know prev_close + n-day avg volume per symbol. Pushed to client
  for v1 because yfinance already returns the 5-day window in the same call;
  no extra IO. Revisit if additional collectors come online.
- **Keep everything in `t_relay_events` with a `dimension` filter.**
  Rejected: makes `t_relay_events` 50× larger, hits MySQL row count + retention
  cleanup, breaks the boundary that "events = facts/signals, not raw price
  ticks".

## Verification
- Unit tests: `tests/test_quote_movement.py` (14), `tests/test_quote_snapshots_endpoint.py` (8).
- Suite: 170 tests pass.
