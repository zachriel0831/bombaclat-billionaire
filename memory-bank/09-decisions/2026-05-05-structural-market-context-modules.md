# 2026-05-05 Structural Market Context Modules

## Decision
Add market breadth, AI capex, and oil supply/demand as deterministic stored-only `market_context:*` modules instead of feeding only raw news into the daily analysis prompt.

## Rationale
- Market breadth helps distinguish healthy participation from index moves concentrated in mega-cap stocks.
- SEC companyfacts capex gives a repeatable proxy for hyperscaler AI infrastructure spending and free-cash-flow pressure.
- FRED oil-price facts and optional EIA inventory facts provide a structured input for energy-shock and inflation-risk scoring.
- All three modules preserve the existing `t_relay_events` contract, so downstream analysis can consume them without schema changes.

## Source Contract
- Market breadth: `source=market_context:market_breadth`, category `market_breadth`.
- AI capex: `source=market_context:sec_companyfacts`, category `ai_capex`; requires `SEC_USER_AGENT`.
- Oil supply/demand: `source=market_context:fred_energy` for `oil_price` and `oil_supply_demand`; `source=market_context:eia` for `oil_inventory` when `EIA_API_KEY` is configured.

## Operational Note
If a source is unavailable, the collector records an explicit `raw_json.failures` entry on the `market_context:collector` summary event rather than silently dropping the module.
