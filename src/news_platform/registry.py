"""TW 媒體 metadata + 第一批社會新聞 feed 來源表。

political_camp: pan_green | pan_blue | mixed | neutral
china_alignment: critical | neutral | beijing_friendly | unknown

URL 為預設值；若官方改路徑，可由 env (`NEWSPF_FEED_<SOURCE_ID>_<CATEGORY>`)
覆寫，例如 `NEWSPF_FEED_LTN_SOCIETY=https://...`。
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SourceMeta:
    source_id: str
    name: str
    country: str
    political_camp: str
    china_alignment: str


@dataclass(frozen=True)
class FeedSpec:
    """單一來源 + 單一分類的抓取設定。

    kind=``rss`` 走 RSS / Atom 解析；kind=``sitemap`` 走 Google News sitemap 解析
    並用 ``path_filter`` 篩出指定分類路徑（例：TVBS 的 `/local/` 對應社會新聞）。
    """

    source_id: str
    category: str
    kind: str
    url: str
    path_filter: str | None = None


TW_SOURCES: list[SourceMeta] = [
    SourceMeta(
        source_id="ltn",
        name="自由時報",
        country="TW",
        political_camp="pan_green",
        china_alignment="critical",
    ),
    SourceMeta(
        source_id="ettoday",
        name="ETtoday新聞雲",
        country="TW",
        political_camp="mixed",
        china_alignment="neutral",
    ),
    SourceMeta(
        source_id="tvbs",
        name="TVBS新聞網",
        country="TW",
        political_camp="pan_blue",
        china_alignment="neutral",
    ),
    SourceMeta(
        # 公營通訊社，作為政治光譜的中立基準。
        source_id="cna",
        name="中央通訊社",
        country="TW",
        political_camp="neutral",
        china_alignment="neutral",
    ),
    SourceMeta(
        # 旺中系，補回 pan_blue 第二家（替代條款衝突的 UDN）。
        source_id="ebc",
        name="東森新聞",
        country="TW",
        political_camp="pan_blue",
        china_alignment="beijing_friendly",
    ),
]


_DEFAULT_TW_SOCIETY_FEEDS: list[FeedSpec] = [
    FeedSpec(
        source_id="ltn",
        category="society",
        kind="rss",
        url="https://news.ltn.com.tw/rss/society.xml",
    ),
    FeedSpec(
        source_id="ettoday",
        category="society",
        kind="rss",
        url="https://feeds.feedburner.com/ettoday/society",
    ),
    FeedSpec(
        # TVBS 已停掉所有 RSS endpoint；改吃 Google News sitemap，
        # 並用 path_filter="/local/" 抓他們的社會分類（站內叫「在地」）。
        source_id="tvbs",
        category="society",
        kind="sitemap",
        url="https://news.tvbs.com.tw/crontab/sitemap/latest",
        path_filter="/local/",
    ),
    FeedSpec(
        source_id="cna",
        category="society",
        kind="rss",
        url="https://feeds.feedburner.com/rsscna/social",
    ),
    FeedSpec(
        # EBC 沒有官方 RSS，但 sitemap 有清楚的 /news/society/ 路徑。
        source_id="ebc",
        category="society",
        kind="sitemap",
        url="https://news.ebc.net.tw/sitemap/realtime.xml",
        path_filter="/news/society/",
    ),
]


def tw_society_feeds() -> list[FeedSpec]:
    """回傳 TW 社會新聞 feed 清單，env 可覆寫單一條目 URL。"""
    overridden: list[FeedSpec] = []
    for spec in _DEFAULT_TW_SOCIETY_FEEDS:
        env_key = f"NEWSPF_FEED_{spec.source_id.upper()}_{spec.category.upper()}"
        url = os.getenv(env_key, spec.url).strip() or spec.url
        overridden.append(
            FeedSpec(
                source_id=spec.source_id,
                category=spec.category,
                kind=spec.kind,
                url=url,
                path_filter=spec.path_filter,
            )
        )
    return overridden


def source_meta(source_id: str) -> SourceMeta | None:
    for meta in TW_SOURCES:
        if meta.source_id == source_id:
            return meta
    return None
