# Fixed Market Analysis Watch Pool

## Date
2026-05-11

## Decision
`market_analysis` no longer treats the individual-stock section as model-selected Taiwan stock recommendations.

It uses a fixed five-stock watch pool:

| ticker | name | market | role |
|---|---|---|---|
| `2330` | 台積電 | TWSE | semiconductor mega-cap / AI cycle proxy |
| `2603` | 長榮 | TWSE | shipping / freight-rate proxy |
| `2882` | 國泰金 | TWSE | financial / rate-insurance proxy |
| `1605` | 華新 | TWSE | cable / copper-infrastructure proxy |
| `4956` | 光鋐 | TPEX | small semiconductor packaging proxy |

## Rationale
The goal is stable monitoring, not ticker discovery. A fixed pool lets middle-office, frontend, and future stock monitor services compare the same names over time and avoid user-facing "AI stock pick" semantics.

## Boundaries
- The model may analyze state, risks, levels, and data gaps for the fixed pool.
- The model must not introduce substitute Taiwan tickers.
- If evidence is insufficient, mark data gap or neutral watch state.
- `t_trade_signals` remains the machine-readable watch/signal table and starts rows as `pending_review`.
- No row is an order. Risk gate, review, trigger handling, and broker execution remain separate layers.

## Operational Contract
- `TWSE_MOPS_TRACKED_CODES=2330,2603,2882,1605`
- `MARKET_CONTEXT_TW_YAHOO_SYMBOLS=2330.TW:台積電,2603.TW:長榮,2882.TW:國泰金,1605.TW:華新,4956.TWO:光鋐`
- UI wording should use `今日個股觀察` / fixed watch pool language, not model recommendation language.
