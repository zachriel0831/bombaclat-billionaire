# LINE Weekly Brief Format

Format-only asset. Python generates the text; downstream Java owns LINE delivery and webhook behavior.

## Weekly Brief Shape

1. 市場主線
2. 跨資產訊號
3. 台股傳導
4. AI 與科技鏈觀察
5. 原物料與匯率
6. 下週觀察重點
7. 反證與觀察限制

## Daily Market Analysis Override

Daily `market_analysis` uses this visible order:

`今日主命題` -> `三個證據` -> `市場正在定價什麼` -> `台股傳導` -> `反證條件` -> `風險與觀察限制`

- `今日主命題` 一句話說清楚市場現在交易的是什麼、台股偏多/偏空/中性，以及最大不確定性。
- `三個證據` 必須剛好三點，每點連接：來源事實 -> 市場機制 -> 為何現在重要。
- `市場正在定價什麼` 說明哪些預期已經反映、哪些仍可能重估。
- `台股傳導` 只能以 NVIDIA、台積電、Magnificent Seven / 美股七巨頭等權值股作傳導例子，不做進出場建議。
- 不得新增 `台股配置` 或 `今日個股觀察`。
- 若資料過期或不足，降低信心並改寫為觀察限制；不要在可見文字寫「資料不足」、「缺漏」、「需等待更新」或內部流程原因。

## Format Rules

- 短段落，避免牆狀文字。
- 數據集中用條列，先講市場意義，再放數字。
- 不顯示內部欄位、代碼、資料表名、模型名、任務名或 API/guard 名稱。
- 不顯示任何 snake_case 欄位、排程代碼、來源代碼或稽核欄位。
- LINE 推播摘要只放一句話與連結，不塞完整文章。
