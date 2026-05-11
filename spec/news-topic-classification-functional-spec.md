# 台灣社會議題追蹤器：新聞分類功能規格

## 1. 產品定位
本功能不是新聞 App 的一般分類，而是「台灣社會議題追蹤器」的基礎層。

- 新聞是證據
- 議題是容器
- 分類結果是後續時間軸、情緒聚合、媒體行為觀察的共用索引

## 2. 第一階段範圍
先支援台灣社會新聞與政治新聞的議題分類。

收集類別：
- `society`：社會新聞
- `politics`：政治新聞

CLI / 環境控制：
- 預設收 `society,politics`
- 可用 `--categories politics` 或 `NEWSPF_CATEGORIES=politics` 只抓政治新聞

MVP 議題：
- `drunk_driving_accident`：酒駕毒駕／車禍傷亡
- `fraud`：詐騙
- `low_birthrate`：少子化
- `judicial_injustice`：司法量刑不公
- `healthcare_burden`：醫護過勞／醫療崩潰
- `housing_justice`：高房價／居住正義
- `drug_abuse`：新興毒品／校園毒品

## 3. 分類流程
```text
crawler
  ↓
t_news_articles
  ↓
KeywordWorker
  ↓ keywords_json
TopicWorker
  ↓ rule topics_json
TopicLlmFallbackWorker（可選）
  ↓ llm topics_json
```

流程規則：
- crawler 只負責收新聞，不做議題判斷
- `t_news_articles.category` 保留來源分類，政治新聞仍沿用同一張文章表
- `KeywordWorker` 先補 `keywords_json`
- `TopicWorker` 使用詞典規則分類
- 規則沒命中時，依 `category` 暫歸一般新聞：
  - `society` → `general_social_news` / 一般社會新聞
  - `politics` → `general_politics_news` / 一般政治新聞
- LLM fallback 可處理 category-specific general topic 且 `topic_classified_by IN (NULL,'rule')` 的文章，嘗試補判成更明確議題
- LLM fallback 跑完後，無論有無命中，都設 `topic_classified_by='llm'`

## 4. LLM fallback 策略
預設關閉。啟用後只處理規則沒分類到的新聞。

Provider 順序：
1. OpenAI `gpt-5-nano`
2. Anthropic `claude-haiku-4-5-20251001`

切換條件：
- OpenAI API key 不存在
- OpenAI 401 / 403 / 429 / 5xx
- OpenAI timeout
- OpenAI 回傳格式不合法

LLM 只回一個主議題或 `none`。不做多議題，避免兜底層過度擴張。

## 5. 前端顯示規則
文章列表：
- 若 `topics_json` 有值，顯示第一個 topic 為主議題
- 若有多個 topic，顯示主議題 + 次議題數量
- `source='rule'` 不需要特別標示
- `source='llm'` 可在中台顯示「AI 補判」，前台可不顯示

未分類狀態：
- `topics_json IS NULL`：尚未分類
- `topics_json[0].topic_id='general_social_news' AND topic_classified_by='rule'`：規則未命中，暫歸一般社會新聞，可等待 LLM 或人工審查
- `topics_json[0].topic_id='general_social_news' AND topic_classified_by='llm'`：規則與 LLM 都未命中，維持一般社會新聞
- `topics_json[0].topic_id='general_politics_news' AND topic_classified_by='rule'`：規則未命中，暫歸一般政治新聞，可等待 LLM 或人工審查
- `topics_json[0].topic_id='general_politics_news' AND topic_classified_by='llm'`：規則與 LLM 都未命中，維持一般政治新聞

## 6. 中台操作建議
中台應提供：
- 依 topic 篩選文章
- 查看分類來源：rule / llm
- 查看 LLM reason
- 查看 `general_social_news` / `general_politics_news` 文章，作為詞典補強與人工審查池
- 人工修正分類
- 匯出誤判/漏判案例供詞典維護

人工修正不在本次後端實作範圍，但資料結構已保留 `source` 以便未來加入 `manual`。

## 7. 後續 Phase
- Phase 2：同 topic 時間軸
- Phase 3：topic 層級情緒曲線
- Phase 4：同 source + topic + 時間窗口洗版偵測
- Phase 5：stance / 反方觀點推薦
