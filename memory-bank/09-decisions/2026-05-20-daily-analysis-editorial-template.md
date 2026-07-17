# Daily Analysis Editorial Template

## Context

After several days of generated daily market analysis, the visible output was too macro-dense and sometimes did not answer the retail-investor question: what should I watch today?

## Decision

Daily `market_analysis` reports use the author-style visible flow:

1. `今日主命題`
2. `三個證據`
3. `市場正在定價什麼`
4. `台股傳導`
5. `反證條件`
6. `風險與觀察限制`

`三個證據` must contain exactly three bullets. Each bullet should connect `資料事實 -> 傳導機制 -> 為什麼現在重要`. `市場正在定價什麼` must explain what expectations are already in prices and what still has room for repricing. `反證條件` must state what would make the thesis wrong.

As of 2026-05-25, daily visible reports must not include a dedicated `台股配置` section and must not append the deterministic `## 今日個股觀察` fixed-pool section. The fixed-pool / `t_trade_signals` flow may continue as machine-readable downstream context, but the daily body should focus on macro and industry/sector interpretation. Individual companies may be mentioned only as mega-cap transmission examples such as NVIDIA, TSMC, or Magnificent Seven / 美股七巨頭.

As of 2026-06-25, daily visible reports must translate internal context labels into reader-facing Chinese. Do not expose source labels, table names, snake_case fields, scheduled task names, provider names, guard names, or custom score labels; describe the market implication instead, such as `盤前市場環境資料顯示...` or `流動性與風險指標偏向支撐風險資產...`.

As of 2026-07-17, this rule also covers table names, API/guard implementation notes, and telemetry terms. Visible reports must not show database table names, structured telemetry field names, provider/API notes, guard names, or sentences that describe how the system repaired or generated the report. Translate those into reader-facing phrasing such as `本次分析主要依據本地新聞、行情與公開資料` or `部分即時外部資料未納入`.

Pushed daily reports should usually land around 800-1400 Chinese characters. Close-window digests and thin-data windows may be shorter, but visible text must still preserve the section order and avoid internal labels.

As of 2026-07-17, the clean daily visible order is:

1. `今日主命題`
2. `三個證據`
3. `市場正在定價什麼`
4. `台股傳導`
5. `反證條件`
6. `風險與觀察限制`

`三個證據` must contain exactly three bullets. Each bullet should connect source fact -> market mechanism -> why it matters now. The report should read like a professional market column: decisive thesis first, then evidence, repricing, Taiwan transmission, invalidation, and reader-facing observation limits.

## Consequences

- Multi-stage Stage4 and legacy fallback prompts share the same visible section order.
- The first section must state a clear investable thesis, not just summarize headlines.
- Evidence, pricing, transmission, and invalidation sections must translate facts into Taiwan-market implications.
- Daily visible output should not contain entry, stop-loss, or target-price language.
- The delivery/signal trust gate is implemented separately in `2026-05-20-claim-verifier-trust-gate.md`.
