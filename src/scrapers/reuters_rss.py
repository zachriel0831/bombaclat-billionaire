"""
Reuters Business News RSS Scraper
Source: Reuters RSS feeds
Output: POST → http://localhost:18090/events → MySQL t_relay_events

依賴套件 (標準庫即可):
    requests, xml.etree.ElementTree (built-in)

執行:
    python scrapers/reuters_rss.py
"""

import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

# relay_client 在 src/ 下，確保可 import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from relay_client import push_articles

# ── 設定 ─────────────────────────────────────────────
RSS_FEEDS = [
    {
        "name":      "Reuters Business",
        "source_id": "reuters_business",
        "url":       "https://feeds.reuters.com/reuters/businessNews",
    },
    {
        "name":      "Reuters Markets",
        "source_id": "reuters_markets",
        "url":       "https://feeds.reuters.com/reuters/financials",
    },
    {
        "name":      "Reuters Technology",
        "source_id": "reuters_technology",
        "url":       "https://feeds.reuters.com/reuters/technologyNews",
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


# ── 解析 ─────────────────────────────────────────────
def parse_rss(xml_text: str, source_id: str) -> list[dict]:
    """解析 parse rss 對應的資料或結果。"""
    root    = ET.fromstring(xml_text)
    channel = root.find("channel")
    if channel is None:
        return []

    articles = []
    for item in channel.findall("item"):
        title = item.findtext("title", "").strip()
        link  = item.findtext("link", "").strip()
        desc  = item.findtext("description", "").strip()
        pub   = item.findtext("pubDate", "").strip()

        published_iso = ""
        if pub:
            try:
                published_iso = parsedate_to_datetime(pub).isoformat()
            except Exception:
                published_iso = pub

        if not title or not link:
            continue

        articles.append({
            "title":          title,
            "description":    desc,
            "url":            link,
            "published_time": published_iso,
            "source":         source_id,
        })

    return articles


def fetch_feed(feed: dict) -> list[dict]:
    """抓取 fetch feed 對應的資料或結果。"""
    print(f"  Fetching: {feed['name']} ...")
    try:
        resp = requests.get(feed["url"], headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return parse_rss(resp.text, feed["source_id"])
    except Exception as e:
        print(f"  [ERROR] {feed['name']}: {e}")
        return []


# ── 主程式 ───────────────────────────────────────────
def main():
    """程式入口，負責執行此模組的主要流程。"""
    print("[Reuters RSS] Starting ...")
    all_articles = []

    for feed in RSS_FEEDS:
        articles = fetch_feed(feed)
        all_articles.extend(articles)
        print(f"  → {len(articles)} articles from {feed['name']}")

    # 依發布時間排序（新到舊）
    all_articles.sort(key=lambda x: x["published_time"], reverse=True)
    print(f"[Reuters RSS] 共 {len(all_articles)} 篇文章")

    # 推送到 Relay → MySQL（source_id 已在每篇 article 內，不傳 override）
    push_articles(all_articles)

    # 預覽前 5 筆
    for i, a in enumerate(all_articles[:5], 1):
        print(f"  {i}. [{a['source']}] {a['title']}")
        print(f"     {a['published_time']}")


if __name__ == "__main__":
    main()
