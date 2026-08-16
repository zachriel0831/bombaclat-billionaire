# Daily Analysis Editorial Template

## Context

After several days of generated daily market analysis, the visible output was too macro-dense and sometimes did not answer the retail-investor question: what should I watch today?

## Decision

Daily `market_analysis` reports historically used this fixed visible flow, now superseded by the 2026-08-16 briefing-memo rule below:

1. `今日一句話`
2. `三個檢查點`
3. `市場押注與預期差`
4. `國際消息到台股的傳導`
5. `看錯的條件`
6. `備註`

The old contract required three checkpoint bullets and fixed pricing/transmission/invalidation sections. Treat that as historical context only.

As of 2026-05-25, daily visible reports must not include a dedicated `台股配置` section and must not append the deterministic `## 今日個股觀察` fixed-pool section. The fixed-pool / `t_trade_signals` flow may continue as machine-readable downstream context, but the daily body should focus on macro and industry/sector interpretation. Individual companies may be mentioned only as mega-cap transmission examples such as NVIDIA, TSMC, or Magnificent Seven / 美股七巨頭, never as stock recommendations.

As of 2026-06-25, daily visible reports must translate internal context labels into reader-facing Chinese. Do not expose source labels, table names, snake_case fields, scheduled task names, provider names, guard names, or custom score labels; describe the market implication instead, such as `盤前市場環境資料顯示...` or `流動性與風險指標偏向支撐風險資產...`.

As of 2026-07-17, this rule also covers table names, API/guard implementation notes, and telemetry terms. Visible reports must not show database table names, structured telemetry field names, provider/API notes, guard names, or sentences that describe how the system repaired or generated the report. Translate those into reader-facing phrasing such as `本次分析主要依據本地新聞、行情與公開資料` or `部分即時外部資料未納入`.

Pushed daily reports should usually land around 700-1200 Chinese characters. Close-window digests and thin-data windows may be shorter, but visible text must still preserve thesis/evidence/transmission/invalidation content and avoid internal labels.

As of 2026-07-31, the previous clean daily visible order was:

1. `今日一句話`
2. `三個檢查點`
3. `市場押注與預期差`
4. `國際消息到台股的傳導`
5. `看錯的條件`
6. `備註`

That section order was retired on 2026-08-16. The lasting requirement is that the report reads like a professional market column: decisive thesis first, then evidence, repricing, Taiwan transmission, invalidation, and reader-facing uncertainty where useful.

As of 2026-08-02, daily reports may trial a trigger-first rhythm inside the same six section titles: `今日一句話` may start with `結論先講`, `市場押注與預期差` may include `先看區間邊界`, and `看錯的條件` may include `現在只看 N 件事` where N is the needed count of evidence-backed triggers. These are thesis-invalidation conditions and observation boundaries, not stock recommendations, entries, stop-losses, take-profits, or order instructions.

As of 2026-08-16, the fixed six-title daily contract is retired because it made every report read like a template. Daily visible reports now use a flexible briefing-memo shape:

1. Opening thesis: what the market is trading now, Taiwan-market bias, and the largest uncertainty.
2. Evidence chain: the strongest 2-4 facts, each connected to mechanism and present market relevance. Bullets are optional and must not be forced to exactly three.
3. Taiwan transmission: how rates, USD, oil, SOX/AI, geopolitics, liquidity, or consumer demand pass into Taiwan sectors and major proxies.
4. Repricing and invalidation: what is already reflected in prices, what can still move, and what would make the thesis wrong.
5. Reader-facing caveat only when useful, phrased as uncertainty instead of internal data/process limitations.

Avoid visible fixed labels such as `今日一句話`, `三個檢查點`, `市場押注與預期差`, `國際消息到台股的傳導`, `先看區間邊界`, or `現在只看 N 件事` unless the user explicitly asks for that format. Natural headings are allowed, but they should change with the evidence window.

## Consequences

- Multi-stage Stage4 and legacy fallback prompts must share the same briefing-memo shape.
- The first section must state a clear investable thesis, not just summarize headlines.
- Evidence, pricing, transmission, and invalidation sections must translate facts into Taiwan-market implications.
- Daily visible output should not contain stock recommendations, buy/watchlist candidates, entry, stop-loss, or target-price language.
- The old fixed sixth section `備註` is no longer required; caveats should appear only when they help the reader.
- The retired trigger-first trial must not reappear by default. Keep the product boundary: no visible `開多`, `開空`, `止盈`, `止損`, `入場區間`, or order-level commands.
- The delivery/signal trust gate is implemented separately in `2026-05-20-claim-verifier-trust-gate.md`.
