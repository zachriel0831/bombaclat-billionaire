# 新聞議題分類操作規格

## 1. 環境變數
必要：

```env
NEWSPF_MYSQL_ENABLED=true
NEWSPF_MYSQL_HOST=127.0.0.1
NEWSPF_MYSQL_PORT=3306
NEWSPF_MYSQL_USER=root
NEWSPF_MYSQL_PASSWORD=...
NEWSPF_MYSQL_DATABASE=news_platform
NEWSPF_CATEGORIES=society,politics
```

LLM fallback 選用：

```env
NEWSPF_TOPIC_LLM_ENABLED=false
NEWSPF_TOPIC_LLM_PROVIDER_ORDER=openai,anthropic
NEWSPF_TOPIC_OPENAI_MODEL=gpt-5-nano
NEWSPF_TOPIC_ANTHROPIC_MODEL=claude-haiku-4-5-20251001
NEWSPF_TOPIC_LLM_BATCH_SIZE=50
NEWSPF_TOPIC_LLM_MIN_CONFIDENCE=0.55
NEWSPF_TOPIC_OPENAI_API_KEY=
NEWSPF_TOPIC_ANTHROPIC_API_KEY=
```

若未設定 topic 專用 key，會 fallback 讀：
- OpenAI：`OPENAI_API_KEY`
- Anthropic：`ANTHROPIC_API_KEY`

## 2. 手動執行
只抓新聞：

```powershell
$env:PYTHONPATH='src'; python -m news_platform.main --once
```

只抓政治新聞：

```powershell
$env:PYTHONPATH='src'; python -m news_platform.main --once --categories politics
```

回填關鍵字與規則分類：

```powershell
$env:PYTHONPATH='src'; python -m news_platform.main --extract-keywords --classify-topics
```

只跑 LLM fallback：

```powershell
$env:PYTHONPATH='src'; python -m news_platform.main --llm-topic-fallback
```

完整長駐：

```powershell
$env:PYTHONPATH='src'; python -m news_platform.main --loop
```

## 3. 成本控制
- LLM fallback 預設關閉
- 只送 `general_social_news/general_politics_news AND topic_classified_by IN (NULL,'rule')`
- `topic_classified_by='llm'` 的一般新聞不會重送
- 可用 `NEWSPF_TOPIC_LLM_BATCH_SIZE` 控制每批送出量
- 可用 `NEWSPF_TOPIC_LLM_MIN_CONFIDENCE` 控制低信心結果是否接受

## 4. 監控指標
建議中台定期統計：

```sql
SELECT topic_classified_by, COUNT(*)
FROM t_news_articles
WHERE topics_json IS NOT NULL
GROUP BY topic_classified_by;
```

一般新聞比例：

```sql
SELECT
  COUNT(*) AS classified_count,
  SUM(JSON_UNQUOTE(JSON_EXTRACT(topics_json, '$[0].topic_id')) = 'general_social_news') AS general_social_count,
  SUM(JSON_UNQUOTE(JSON_EXTRACT(topics_json, '$[0].topic_id')) = 'general_politics_news') AS general_politics_count
FROM t_news_articles
WHERE topics_json IS NOT NULL;
```

LLM 補判比例：

```sql
SELECT COUNT(*)
FROM t_news_articles
WHERE topic_classified_by = 'llm'
  AND JSON_LENGTH(topics_json) > 0;
```

## 5. 已有文章修正
- 新分類規則只自動套用新文章；重複抓取不覆寫既有文章分類或人工修正。
- 回填先限定文章 ID、確認目前分類來源為 `rule`，保存 category/raw/topics/classified_at 的 before-image，再 dry-run 新 category/topics。
- 正式回填須在同一交易鎖定並比對 before-image，原來源分類留在 raw_json；重新讀取 DB，並確認社會 API 可查到、政治 API 不再回傳。作者與公共紀錄關聯保持不變。
- 長駐 `news_platform.main --loop` 須重新載入程式；低頻單次採集下一次執行即使用新規則。

## 6. 驗收標準
- 新文章進入 `t_news_articles`
- 政治新聞預設寫入 `category='politics'`；明確預售屋契約查核例外寫入 `society`，原來源分類保留在 raw_json
- 關鍵字完成後 `keywords_json IS NOT NULL`
- 規則分類完成後 `topics_json IS NOT NULL`
- 規則未命中時暫歸 `general_social_news` 或 `general_politics_news`
- LLM fallback 啟用時，規則 fallback 文章會改為具體 LLM topic 或 `topic_classified_by='llm'` 的 category-specific general topic
- LLM 命中結果包含 `source='llm'`、`provider`、`model`
