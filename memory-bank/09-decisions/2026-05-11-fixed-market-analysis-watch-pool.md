# Fixed Market Analysis Watch Pool

## Date
2026-05-11

## Superseded
Superseded on 2026-05-16 by `memory-bank/09-decisions/2026-05-16-ten-stock-observation-template.md`, then superseded again on 2026-07-20 by dynamic evidence-backed daily Taiwan candidates. The old fixed pool is historical only.

## Decision
Superseded on 2026-06-02 by `2026-06-02-dynamic-intraday-candidate-pipeline.md`.

This fixed-pool decision is historical. The fixed pool was an observation/debugging aid, not the final trading-candidate policy.

Target direction: Codex should generate dynamic daily Taiwan intraday / short-swing candidates from relay events, market context, quote evidence, historical/RAG context, and model judgment.

Historical 2026-05-11 pool used five stocks:

| ticker | name | market | role |
|---|---|---|---|
| `2330` | 台積電 | TWSE | semiconductor mega-cap / AI cycle proxy |
| `2603` | 長榮 | TWSE | shipping / freight-rate proxy |
| `2882` | 國泰金 | TWSE | financial / rate-insurance proxy |
| `1605` | 華新 | TWSE | cable / copper-infrastructure proxy |
| `4956` | 光鋐 | TPEX | small semiconductor packaging proxy |

## Historical Rationale
The goal is stable monitoring, not ticker discovery. A fixed pool lets middle-office, frontend, and future stock monitor services compare the same names over time and avoid user-facing "AI stock pick" semantics.

## Superseded Boundaries
- The model may analyze state, risks, levels, and data gaps for the fixed pool.
- The model must not introduce substitute Taiwan tickers.
- If evidence is insufficient, mark data gap or neutral watch state.
- `t_trade_signals` remains the machine-readable watch/signal table and starts rows as `pending_review`.
- No row is an order. Risk gate, review, trigger handling, and broker execution remain separate layers.

## Historical Operational Contract
- `TWSE_MOPS_TRACKED_CODES=2330,2603,2882,1605`
- `MARKET_CONTEXT_TW_YAHOO_SYMBOLS=2330.TW:台積電,2603.TW:長榮,2882.TW:國泰金,1605.TW:華新,4956.TWO:光鋐`
- UI wording used `今日個股觀察` / fixed watch pool language historically. Current daily strategy output must use dynamic candidate language and must not imply a static universe.
