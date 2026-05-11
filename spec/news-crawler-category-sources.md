# 新聞爬蟲分類來源規格

## 1. 目的
`news_platform` 目前收台灣社會與政治新聞，兩者共用同一條資料處理流程：

```text
source feed/list → t_news_articles.category → KeywordWorker → TopicWorker → optional LLM fallback
```

不新增文章-議題關聯表；分類結果仍寫在 `t_news_articles.topics_json`。

## 2. 支援類別
| category | 顯示語意 | 規則未命中 fallback |
|---|---|---|
| `society` | 社會新聞 | `general_social_news` / 一般社會新聞 |
| `politics` | 政治新聞 | `general_politics_news` / 一般政治新聞 |

預設抓取 `society,politics`。可用：

```powershell
$env:PYTHONPATH='src'; python -m news_platform.main --once --categories politics
```

或：

```env
NEWSPF_CATEGORIES=politics
```

## 3. 政治新聞來源
| source_id | 類型 | URL/規則 |
|---|---|---|
| `ltn` | RSS | `https://news.ltn.com.tw/rss/politics.xml` |
| `ettoday` | HTML list | `https://www.ettoday.net/news/news-list-{date}-1.htm`，只收標籤為「政治」的列 |
| `tvbs` | Google News sitemap | `https://news.tvbs.com.tw/crontab/sitemap/latest` + path contains `/politics/` |
| `cna` | RSS | `https://feeds.feedburner.com/rsscna/politics` |
| `pts` | HTML category page | `https://news.pts.org.tw/category/1` |
| `ebc` | sitemap | `https://news.ebc.net.tw/sitemap/realtime.xml` + path contains `/news/politics/` |

ETtoday politics list 在部分 Windows/OpenSSL build 會因站方憑證缺 SKI 導致 Python 驗證失敗；程式只針對這個公開讀取來源使用 source-scoped SSL verification workaround。

公視 PTS 使用分類頁，不使用總 RSS，避免總 RSS 沒有 society/politics 分類欄位而造成跨分類重複。社會分類使用 `https://news.pts.org.tw/category/7`。

## 4. 中台/前端使用
- 列表可用 `category` 做第一層來源分類。
- 主議題仍取 `topics_json[0]`。
- `general_politics_news` 表示「已處理，但沒有命中特定社會議題」，不是 worker 尚未執行。
- 尚未處理只看 `topics_json IS NULL`。
