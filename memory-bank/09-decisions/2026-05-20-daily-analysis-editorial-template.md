# Daily Analysis Editorial Template

## Context

After several days of generated daily market analysis, the visible output was too macro-dense and sometimes did not answer the retail-investor question: what should I watch today?

## Decision

Daily `market_analysis` reports use the product-editor visible flow:

1. `今日一句話`
2. `三個檢查點`
3. `總經與流動性`
4. `景氣循環`
5. `國際新聞傳導`
6. `產業板塊解析`
7. `風險與資料缺口`

`三個檢查點` must contain exactly three observable checks. `國際新聞傳導` should use `事件 -> 影響變數 -> 台股族群 -> 確認/失效` when there is supporting evidence.

As of 2026-05-25, daily visible reports must not include a dedicated `台股配置` section and must not append the deterministic `## 今日個股觀察` fixed-pool section. The fixed-pool / `t_trade_signals` flow may continue as machine-readable downstream context, but the daily body should focus on macro and industry/sector interpretation. Individual companies may be mentioned only as mega-cap transmission examples such as NVIDIA, TSMC, or Magnificent Seven / 美股七巨頭.

As of 2026-06-25, daily visible reports must translate internal context labels into reader-facing Chinese. Do not expose `market scorecard`, `scorecard +4`, `market_context`, `market_context:scorecard`, `07:20 market_context`, `analysis_slot`, `scheduled_time_local`, or `raw_json`; describe the market implication instead, such as `盤前市場環境資料顯示...` or `流動性與風險指標偏向支撐風險資產...`.

## Consequences

- Multi-stage Stage4 and legacy fallback prompts share the same visible section order.
- The first two sections must answer what a Taiwan investor should watch before macro detail.
- Macro, cycle, international-news, and industry/sector sections must translate evidence into Taiwan-market implications.
- Daily visible output should not contain entry, stop-loss, or target-price language.
- The failed `claim_verifier` delivery/signal block is implemented separately in `2026-05-20-claim-verifier-trust-gate.md`.
