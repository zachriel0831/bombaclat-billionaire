"""
BBC Business News Scraper
Source: https://www.bbc.com/business
Output: POST → http://localhost:18090/events → MySQL t_relay_events

依賴套件:
    pip install requests beautifulsoup4 lxml

執行:
    python scrapers/bbc_business.py
"""

import os
import re
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

# relay_client 在 src/ 下，確保可 import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from relay_client import push_articles

# ── 設定 ─────────────────────────────────────────────
TARGET_URL = "https://www.bbc.com/business"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
ARTICLE_PATTERN = re.compile(r"bbc\.com/(news|business)/articles/[a-z0-9]+$")
SOURCE_ID = "bbc_business"


# ── 爬取 ─────────────────────────────────────────────
def fetch_page(url: str) -> BeautifulSoup:
    """抓取 fetch page 對應的資料或結果。"""
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "lxml")


def extract_articles(soup: BeautifulSoup) -> list[dict]:
    """
    BBC 使用動態 data-testid card，同時也可用 article tag 或 class*=Card。
    抓 h3/h2 + a[href*='/articles/'] 組合。
    """
    results = []
    seen_urls = set()

    selectors = [
        '[data-testid="dundee-card"]',
        '[data-testid="card"]',
        "article",
        '[class*="Card"]',
    ]

    cards = []
    for sel in selectors:
        cards.extend(soup.select(sel))

    for card in cards:
        link    = card.select_one('a[href*="/articles/"]')
        heading = card.select_one("h3, h2")

        if not link or not heading:
            continue

        url = link.get("href", "")
        if url.startswith("/"):
            url = "https://www.bbc.com" + url

        if not ARTICLE_PATTERN.search(url):
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)

        desc_el = card.select_one("p")
        description = desc_el.get_text(strip=True) if desc_el else ""

        time_el = card.select_one("time, [data-testid*='time']")
        time_str = ""
        if time_el:
            time_str = time_el.get("datetime") or time_el.get_text(strip=True)

        results.append({
            "title":          heading.get_text(strip=True),
            "description":    description,
            "url":            url,
            "published_time": time_str,
            "source":         SOURCE_ID,
        })

    return results


# ── 主程式 ───────────────────────────────────────────
def main():
    """程式入口，負責執行此模組的主要流程。"""
    print(f"[BBC Business] Fetching {TARGET_URL} ...")
    soup     = fetch_page(TARGET_URL)
    articles = extract_articles(soup)
    print(f"[BBC Business] 抓到 {len(articles)} 篇文章")

    # 推送到 Relay → MySQL
    push_articles(articles, source_override=SOURCE_ID)

    # 預覽前 5 筆
    for i, a in enumerate(articles[:5], 1):
        print(f"  {i}. {a['title']}")
        print(f"     {a['url']}")


if __name__ == "__main__":
    main()
