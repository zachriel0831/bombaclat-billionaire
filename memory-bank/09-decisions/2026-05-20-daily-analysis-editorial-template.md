# Daily Analysis Editorial Template

## Context

After several days of generated daily market analysis, the visible output was too macro-dense and sometimes did not answer the retail-investor question: what should I watch today?

## Decision

Daily `market_analysis` reports use the refreshed author-style visible flow:

1. `今日一句話`
2. `三個檢查點`
3. `市場押注與預期差`
4. `國際消息到台股的傳導`
5. `看錯的條件`
6. `觀察限制`

`三個檢查點` must contain exactly three bullets. Each bullet should connect `資料事實 -> 傳導機制 -> 為什麼現在重要`. `市場押注與預期差` must explain what expectations are already in prices and what still has room for repricing. `看錯的條件` must state what would make the thesis wrong.

As of 2026-05-25, daily visible reports must not include a dedicated `台股配置` section and must not append the deterministic `## 今日個股觀察` fixed-pool section. The fixed-pool / `t_trade_signals` flow may continue as machine-readable downstream context, but the daily body should focus on macro and industry/sector interpretation. Individual companies may be mentioned only as mega-cap transmission examples such as NVIDIA, TSMC, or Magnificent Seven / 美股七巨頭.

As of 2026-06-25, daily visible reports must translate internal context labels into reader-facing Chinese. Do not expose source labels, table names, snake_case fields, scheduled task names, provider names, guard names, or custom score labels; describe the market implication instead, such as `盤前市場環境資料顯示...` or `流動性與風險指標偏向支撐風險資產...`.

As of 2026-07-17, this rule also covers table names, API/guard implementation notes, and telemetry terms. Visible reports must not show database table names, structured telemetry field names, provider/API notes, guard names, or sentences that describe how the system repaired or generated the report. Translate those into reader-facing phrasing such as `本次分析主要依據本地新聞、行情與公開資料` or `部分即時外部資料未納入`.

Pushed daily reports should usually land around 800-1400 Chinese characters. Close-window digests and thin-data windows may be shorter, but visible text must still preserve the section order and avoid internal labels.

As of 2026-07-31, the clean daily visible order is:

1. `今日一句話`
2. `三個檢查點`
3. `市場押注與預期差`
4. `國際消息到台股的傳導`
5. `看錯的條件`
6. `觀察限制`

`三個檢查點` must contain exactly three bullets. Each bullet should connect source fact -> market mechanism -> why it matters now. The report should read like a professional market column: decisive thesis first, then evidence, repricing, Taiwan transmission, invalidation, and reader-facing observation limits.

As of 2026-08-02, daily reports may trial a trigger-first rhythm inside the same six section titles: `今日一句話` may start with `結論先講`, `市場押注與預期差` may include `先看區間邊界`, and `看錯的條件` may include `現在只看兩件事` with one upside trigger and one downside trigger. Any level must be evidence-backed and framed as an observation boundary, not an entry, stop-loss, take-profit, or order instruction.

## Consequences

- Multi-stage Stage4 and legacy fallback prompts share the same visible section order.
- The first section must state a clear investable thesis, not just summarize headlines.
- Evidence, pricing, transmission, and invalidation sections must translate facts into Taiwan-market implications.
- Daily visible output should not contain entry, stop-loss, or target-price language.
- The trigger-first trial borrows pacing from retail market dashboards but keeps the product boundary: no visible `開多`, `開空`, `止盈`, `止損`, `入場區間`, or order-level commands.
- The delivery/signal trust gate is implemented separately in `2026-05-20-claim-verifier-trust-gate.md`.
