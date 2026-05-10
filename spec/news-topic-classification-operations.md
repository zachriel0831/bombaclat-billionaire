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
- 只送 `general_social_news AND topic_classified_by IN (NULL,'rule')`
- `topic_classified_by='llm'` 的一般社會新聞不會重送
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

一般社會新聞比例：

```sql
SELECT
  COUNT(*) AS classified_count,
  SUM(JSON_UNQUOTE(JSON_EXTRACT(topics_json, '$[0].topic_id')) = 'general_social_news') AS general_social_count
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

## 5. 驗收標準
- 新文章進入 `t_news_articles`
- 關鍵字完成後 `keywords_json IS NOT NULL`
- 規則分類完成後 `topics_json IS NOT NULL`
- 規則未命中時暫歸 `general_social_news`
- LLM fallback 啟用時，規則 fallback 文章會改為具體 LLM topic 或 `topic_classified_by='llm'` 的 `general_social_news`
- LLM 命中結果包含 `source='llm'`、`provider`、`model`
