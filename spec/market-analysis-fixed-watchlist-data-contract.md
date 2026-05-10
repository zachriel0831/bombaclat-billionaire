# Market Analysis 固定五檔資料契約

## 1. Structured JSON

`t_market_analyses.structured_json.stock_watch` 仍沿用既有欄位，但語意改為固定監控池，不是自由推薦清單。

每列允許 ticker：

```json
["2330", "2603", "2882", "1605", "4956"]
```

建議欄位：

```json
{
  "ticker": "2330",
  "name": "台積電",
  "market": "TWSE",
  "watch_role": "fixed_pool",
  "strategy_type": "swing",
  "direction": "long",
  "entry_zone": {"low": 1000, "high": 1030},
  "take_profit_zone": {"low": 1080, "high": 1120},
  "invalidation": {"price": 980},
  "rationale": "AI 需求與費半脈絡支撐，但需確認量價。",
  "data_gap": null
}
```

資料不足範例：

```json
{
  "ticker": "4956",
  "name": "光鋐",
  "market": "TPEX",
  "watch_role": "fixed_pool",
  "direction": "neutral",
  "entry_zone": null,
  "take_profit_zone": null,
  "invalidation": null,
  "rationale": "與 2330 同半導體主題，但今日缺少足夠量價證據。",
  "data_gap": "缺少近期有效 quote/context evidence"
}
```

## 2. `t_trade_signals`

仍沿用現有表，不另開表。

語意：

- one row per fixed-pool watch item
- `status=pending_review`
- 不是訂單
- 不是模型自由推薦結果

限制：

- `ticker` must be one of `2330`, `2603`, `2882`, `1605`, `4956`
- `.TW` / `.TWO` suffix stripped in storage
- `market` 保存 TWSE / TPEX 類型
- `source` 可為 `stock_watch`、`quote_fallback_stock_watch`、`context_fallback_stock_watch`

## 3. 中台 API 建議

列表回傳欄位：

- `analysis_id`
- `analysis_date`
- `analysis_slot`
- `ticker`
- `name`
- `market`
- `sector`
- `size_bucket`
- `liquidity_level`
- `drivers`
- `strategy_type`
- `direction`
- `entry_zone`
- `take_profit_zone`
- `invalidation`
- `rationale`
- `data_gap`
- `status`

前端顯示名稱：

- 固定監控池
- 今日個股觀察
- 觀察條件
- 資料缺口

避免顯示：

- 模型推薦
- 推薦買進
- AI 薦股
