"""TW 媒體 metadata + 社會／政治新聞 feed 來源表。

political_camp: pan_green | pan_blue | mixed | neutral
china_alignment: critical | neutral | beijing_friendly | unknown

URL 為預設值；若官方改路徑，可由 env (`NEWSPF_FEED_<SOURCE_ID>_<CATEGORY>`)
覆寫，例如 `NEWSPF_FEED_LTN_SOCIETY=https://...`。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable


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
    kind=``ettoday_list`` 走 ETtoday 分類列表 HTML 解析。
    kind=``pts_category`` 走公視新聞網分類頁 HTML 解析。
    """

    source_id: str
    category: str
    kind: str
    url: str
    path_filter: str | None = None


SUPPORTED_TW_CATEGORIES = ("society", "politics")


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
        source_id="pts",
        name="公視新聞網",
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
    SourceMeta(
        source_id="newtalk",
        name="Newtalk",
        country="TW",
        political_camp="pan_green",
        china_alignment="critical",
    ),
    SourceMeta(
        source_id="storm",
        name="Storm Media",
        country="TW",
        political_camp="mixed",
        china_alignment="neutral",
    ),
    SourceMeta(
        # 工商時報屬旺中系，以公開 Google News sitemap 補足政策與生活新聞覆蓋。
        source_id="ctee",
        name="工商時報",
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
        source_id="pts",
        category="society",
        kind="pts_category",
        url="https://news.pts.org.tw/category/7",
    ),
    FeedSpec(
        # EBC 沒有官方 RSS，但 sitemap 有清楚的 /news/society/ 路徑。
        source_id="ebc",
        category="society",
        kind="sitemap",
        url="https://news.ebc.net.tw/sitemap/realtime.xml",
        path_filter="/news/society/",
    ),
    FeedSpec(
        source_id="newtalk",
        category="society",
        kind="rss",
        url="https://newtalk.tw/rss/category/14",
    ),
    FeedSpec(
        source_id="storm",
        category="society",
        kind="rss",
        url="https://www.storm.mg/api/getRss/channel_id/9?path=https%3A%2F%2Fwww.storm.mg%2Farticle",
    ),
    FeedSpec(
        # CTEE sitemap URL tail category code 431401 maps to articleSection=生活.
        source_id="ctee",
        category="society",
        kind="sitemap",
        url="https://www.ctee.com.tw/sitemaps/sitemap_newstoday.xml",
        path_filter="-431401",
    ),
]


_DEFAULT_TW_POLITICS_FEEDS: list[FeedSpec] = [
    FeedSpec(
        source_id="ltn",
        category="politics",
        kind="rss",
        url="https://news.ltn.com.tw/rss/politics.xml",
    ),
    FeedSpec(
        # ETtoday 政治沒有穩定 RSS；抓官方分類列表（category id=1）。
        source_id="ettoday",
        category="politics",
        kind="ettoday_list",
        url="https://www.ettoday.net/news/news-list-{date}-1.htm",
    ),
    FeedSpec(
        source_id="tvbs",
        category="politics",
        kind="sitemap",
        url="https://news.tvbs.com.tw/crontab/sitemap/latest",
        path_filter="/politics/",
    ),
    FeedSpec(
        source_id="cna",
        category="politics",
        kind="rss",
        url="https://feeds.feedburner.com/rsscna/politics",
    ),
    FeedSpec(
        source_id="pts",
        category="politics",
        kind="pts_category",
        url="https://news.pts.org.tw/category/1",
    ),
    FeedSpec(
        source_id="ebc",
        category="politics",
        kind="sitemap",
        url="https://news.ebc.net.tw/sitemap/realtime.xml",
        path_filter="/news/politics/",
    ),
    FeedSpec(
        source_id="newtalk",
        category="politics",
        kind="rss",
        url="https://newtalk.tw/rss/category/2",
    ),
    FeedSpec(
        source_id="storm",
        category="politics",
        kind="rss",
        url="https://www.storm.mg/api/getRss/channel_id/7?path=https%3A%2F%2Fwww.storm.mg%2Farticle",
    ),
    FeedSpec(
        # CTEE sitemap URL tail category code 430104 maps to articleSection=要聞.
        source_id="ctee",
        category="politics",
        kind="sitemap",
        url="https://www.ctee.com.tw/sitemaps/sitemap_newstoday.xml",
        path_filter="-430104",
    ),
]


_DEFAULT_TW_FEEDS_BY_CATEGORY: dict[str, list[FeedSpec]] = {
    "society": _DEFAULT_TW_SOCIETY_FEEDS,
    "politics": _DEFAULT_TW_POLITICS_FEEDS,
}


def tw_society_feeds() -> list[FeedSpec]:
    """回傳 TW 社會新聞 feed 清單，env 可覆寫單一條目 URL。"""
    return tw_news_feeds(categories=("society",))


def tw_politics_feeds() -> list[FeedSpec]:
    """回傳 TW 政治新聞 feed 清單，env 可覆寫單一條目 URL。"""
    return tw_news_feeds(categories=("politics",))


def tw_news_feeds(categories: Iterable[str] | None = None) -> list[FeedSpec]:
    """回傳指定分類的 TW 新聞 feed 清單，依 category 順序展開。"""
    wanted = tuple(categories or SUPPORTED_TW_CATEGORIES)
    overridden: list[FeedSpec] = []
    for category in wanted:
        normalized = category.strip().lower()
        if normalized not in _DEFAULT_TW_FEEDS_BY_CATEGORY:
            supported = ", ".join(SUPPORTED_TW_CATEGORIES)
            raise ValueError(f"Unsupported TW news category: {category}. Supported: {supported}")
        for spec in _DEFAULT_TW_FEEDS_BY_CATEGORY[normalized]:
            overridden.append(_with_env_override(spec))
    return overridden


def _with_env_override(spec: FeedSpec) -> FeedSpec:
    env_key = f"NEWSPF_FEED_{spec.source_id.upper()}_{spec.category.upper()}"
    url = os.getenv(env_key, spec.url).strip() or spec.url
    return FeedSpec(
        source_id=spec.source_id,
        category=spec.category,
        kind=spec.kind,
        url=url,
        path_filter=spec.path_filter,
    )


def source_meta(source_id: str) -> SourceMeta | None:
    for meta in TW_SOURCES:
        if meta.source_id == source_id:
            return meta
    return None
