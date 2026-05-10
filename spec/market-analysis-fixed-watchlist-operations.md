# Market Analysis 固定五檔操作規格

## 1. 環境設定

建議固定設定：

```env
TWSE_MOPS_TRACKED_CODES=2330,2603,2882,1605
MARKET_CONTEXT_TW_YAHOO_SYMBOLS=2330.TW:台積電,2603.TW:長榮,2882.TW:國泰金,1605.TW:華新,4956.TWO:光鋐
MARKET_ANALYSIS_EXCLUDED_TICKERS=4749
```

說明：

- `4956` 是 TPEx，使用 Yahoo `.TWO`
- TWSE/MOPS listed-company source 只放上市代碼
- Yahoo context 覆蓋完整五檔

## 2. 產出流程

```text
market_context / quote context
  ↓
market_analysis
  ↓
structured_json.stock_watch 固定五檔
  ↓
t_trade_signals pending_review
  ↓
今日個股觀察
  ↓
future stock monitor service 監聽固定五檔條件
```

## 3. 驗收檢查

每日檢查：

```sql
SELECT ticker, COUNT(*)
FROM t_trade_signals
WHERE analysis_id = :analysis_id
GROUP BY ticker;
```

允許 ticker：

```text
2330
2603
2882
1605
4956
```

不得出現：

- 固定池以外台股
- `4749`
- 沒有 name 的 ticker-only 顯示
- 「模型推薦」類文案

## 4. 監聽服務規則

stock monitor 服務啟動時：

- 載入固定五檔 pool
- 讀取最新 `t_trade_signals` 作為當日參考條件
- 僅監聽固定 pool ticker
- 遇到缺條件的 ticker，維持監控但不觸發交易信號

事件觸發：

- entry zone hit
- invalidation breached
- take-profit zone touched
- volume/price evidence gap

觸發後：

- 寫入 trigger/review 層
- 仍需 risk gate / human review
- 不直接下單

## 5. 文件同步規則

只要固定 pool 改動，需同步更新：

- `README.md`
- `memory-bank/PROJECT_DOCUMENTATION.md`
- `memory-bank/workflows.md`
- `spec/market-analysis-fixed-watchlist-*.md`
- 相關 decision doc
