# 新聞議題分類資料契約

## 1. Table：t_news_articles
本功能沿用原本文章表，不另開關聯表。

新增/使用欄位：

| 欄位 | 型別 | 說明 |
|---|---|---|
| `keywords_json` | JSON NULL | 關鍵字抽取結果 |
| `topics_json` | JSON NULL | 議題分類結果 |
| `topic_classified_by` | VARCHAR(16) NULL | `rule` / `llm` / NULL |
| `topic_classified_at` | DATETIME NULL | 最近一次分類完成時間，UTC |

## 2. topics_json 格式
規則分類命中：

```json
[
  {
    "topic_id": "fraud",
    "label": "詐騙",
    "score": 1.3,
    "source": "rule"
  }
]
```

LLM fallback 命中：

```json
[
  {
    "topic_id": "housing_justice",
    "label": "高房價／居住正義",
    "score": 0.82,
    "source": "llm",
    "provider": "openai",
    "model": "gpt-5-nano",
    "reason": "摘要提到青年買不起房與房價壓力"
  }
]
```

規則未命中，暫歸一般社會新聞：

```json
[
  {
    "topic_id": "general_social_news",
    "label": "一般社會新聞",
    "score": 0.0,
    "source": "rule_fallback",
    "reason": "no_specific_topic_match"
  }
]
```

## 3. 狀態判斷
| 狀態 | 判斷條件 | 前端/中台語意 |
|---|---|---|
| 尚未分類 | `topics_json IS NULL` | worker 尚未處理 |
| 規則命中 | `JSON_LENGTH(topics_json)>0 AND topic_classified_by='rule'` | 詞典分類成功 |
| 規則未命中 | `topics_json[0].topic_id='general_social_news' AND topic_classified_by='rule'` | 暫歸一般社會新聞，可送 LLM fallback |
| LLM 命中 | `JSON_LENGTH(topics_json)>0 AND topic_classified_by='llm'` | AI 補判成功 |
| LLM 未命中 | `topics_json[0].topic_id='general_social_news' AND topic_classified_by='llm'` | 維持一般社會新聞，進人工審查 |

## 4. 查詢範例
待 LLM fallback：

```sql
SELECT id, article_id, title, summary
FROM t_news_articles
WHERE topics_json IS NOT NULL
  AND (
    JSON_LENGTH(topics_json) = 0
    OR JSON_UNQUOTE(JSON_EXTRACT(topics_json, '$[0].topic_id')) = 'general_social_news'
  )
  AND (topic_classified_by IS NULL OR topic_classified_by = 'rule')
ORDER BY published_at DESC, id DESC
LIMIT 50;
```

某議題文章：

```sql
SELECT *
FROM t_news_articles
WHERE JSON_SEARCH(topics_json, 'one', 'fraud', NULL, '$[*].topic_id') IS NOT NULL
ORDER BY published_at DESC;
```

## 5. API 建議回傳格式
若中台或前端 API 包裝文章，建議輸出：

```json
{
  "article_id": "ltn:abc123",
  "title": "標題",
  "summary": "摘要",
  "source_id": "ltn",
  "published_at": "2026-05-11T08:00:00Z",
  "topics": [
    {
      "topic_id": "fraud",
      "label": "詐騙",
      "score": 1.3,
      "source": "rule"
    }
  ],
  "topic_classified_by": "rule",
  "topic_classified_at": "2026-05-11T08:05:00Z"
}
```

## 6. 相容性
`topics_json` 是目前 MVP 查詢來源。

未來若 topic timeline 查詢量變大，可新增 `t_news_article_topics` 關聯表，並保留 `topics_json` 作分類快照。
