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

Daily `market_analysis` uses a briefing-memo shape, not a fixed visible order:

- 先用短段落說清楚市場現在交易的是什麼、台股偏多/偏空/中性，以及最大不確定性。
- 接著用最強的 2-4 個事實串成證據鏈：來源事實 -> 市場機制 -> 為何現在重要。可以條列，也可以短段落，不強迫剛好三點。
- 說明哪些預期已經反映、哪些仍可能重估。
- 說明國際消息如何傳到台股；只能以 NVIDIA、台積電、Magnificent Seven / 美股七巨頭等權值股作傳導例子，不做進出場建議。
- 收尾要有反證條件：哪些資料或市場走勢會讓本次判斷降級。
- 避免可見固定標籤：`今日一句話`、`三個檢查點`、`市場押注與預期差`、`國際消息到台股的傳導`、`先看區間邊界`、`現在只看 N 件事`。若要用標題，標題應依當天資料自然變化。
- 不得新增 `台股配置`、`今日個股觀察`、推薦股票、買進名單或觀察清單。
- 不得寫 `開多`、`開空`、`止盈`、`止損`、`入場區間` 或下單型文字。
- 若資料過期或不足，降低信心並改寫成讀者看得懂的市場不確定性；不要在可見文字寫內部流程原因。

## Format Rules

- 短段落，避免牆狀文字。
- 數據集中用條列，先講市場意義，再放數字。
- 不顯示內部欄位、代碼、資料表名、模型名、任務名或 API/guard 名稱。
- 不顯示任何 snake_case 欄位、排程代碼、來源代碼或稽核欄位。
- LINE 推播摘要只放一句話與連結，不塞完整文章。
