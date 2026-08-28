"""Low-frequency public homepage headline source for international news."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
import logging
import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from news_collector.http_client import http_get_text_with_headers
from news_collector.models import NewsItem
from news_collector.sources.base import NewsSource
from news_collector.utils import stable_id


logger = logging.getLogger(__name__)

_HEADLINE_BLOCKLIST = {
    "advertisement",
    "audio",
    "business",
    "contact us",
    "culture",
    "home",
    "live",
    "more",
    "news",
    "newsletter",
    "opinion",
    "podcasts",
    "privacy policy",
    "sign in",
    "subscribe",
    "technology",
    "video",
    "watch",
    "world",
}
_TRACKING_PARAM_RE = re.compile(r"^(utm_|cmpid$|fbclid$|gclid$|ocid$|cid$)", re.IGNORECASE)
_SUMMARY_TAIL_RE = re.compile(
    r"\s+(?:A|An|Authorities|Experts|He|Her|His|Hundreds|It|Nickolay|Officials|Police|Researchers|She|The|Their|They|Trump's)\b"
)
_CAPTION_PREFIX_RE = re.compile(r"^(?:an aerial view|a photo|a person|people|survivors|us president)\b", re.IGNORECASE)
_CAPTION_TERMS_RE = re.compile(
    r"\b(?:ap photo|appears in court|associated press|attention editors|getty|image|international criminal tribunal|photo|photographer|picture|pictured|reuters|via)\b",
    re.IGNORECASE,
)
_DISALLOWED_PATH_PARTS = (
    "/author/",
    "/authors/",
    "/category/",
    "/live-news/",
    "/newsletter",
    "/podcast",
    "/profile/",
    "/profiles/",
    "/tag/",
    "/topic/",
    "/topics/",
    "/video/",
    "/videos/",
)


@dataclass(frozen=True)
class HomepageHeadlineSite:
    source_id: str
    label: str
    url: str
    article_prefixes: tuple[str, ...]
    path_regex: str


@dataclass(frozen=True)
class _AnchorCandidate:
    href: str
    title: str


@dataclass
class _OpenAnchor:
    href: str
    texts: list[str]


DEFAULT_HOMEPAGE_HEADLINE_SITES = (
    HomepageHeadlineSite(
        "bbc",
        "Homepage: BBC News",
        "https://www.bbc.com/news/world",
        ("https://www.bbc.com/news/", "https://www.bbc.co.uk/news/"),
        r"/news/articles/",
    ),
    HomepageHeadlineSite(
        "reuters",
        "Homepage: Reuters",
        "https://www.reuters.com/",
        (
            "https://www.reuters.com/world/",
            "https://www.reuters.com/business/",
            "https://www.reuters.com/technology/",
            "https://www.reuters.com/markets/",
            "https://www.reuters.com/legal/",
            "https://www.reuters.com/sustainability/",
        ),
        r"/20\d{2}/",
    ),
    HomepageHeadlineSite(
        "ap",
        "Homepage: AP News",
        "https://apnews.com/world-news",
        ("https://apnews.com/article/",),
        r"/article/",
    ),
    HomepageHeadlineSite(
        "guardian",
        "Homepage: The Guardian",
        "https://www.theguardian.com/world",
        ("https://www.theguardian.com/",),
        r"/(world|us-news|business|technology|environment|politics|global-development|science)/20\d{2}/",
    ),
    HomepageHeadlineSite(
        "npr",
        "Homepage: NPR",
        "https://www.npr.org/sections/world/",
        ("https://www.npr.org/",),
        r"/20\d{2}/",
    ),
    HomepageHeadlineSite(
        "cnn",
        "Homepage: CNN",
        "https://www.cnn.com/world",
        ("https://www.cnn.com/",),
        r"/20\d{2}/\d{2}/\d{2}/(africa|americas|asia|europe|middle-east|world)/",
    ),
    HomepageHeadlineSite(
        "fox",
        "Homepage: Fox News",
        "https://www.foxnews.com/world",
        ("https://www.foxnews.com/",),
        r"/(world|politics|us|media|tech|health|science|weather)/",
    ),
    HomepageHeadlineSite(
        "aljazeera",
        "Homepage: Al Jazeera English",
        "https://www.aljazeera.com/news/",
        ("https://www.aljazeera.com/",),
        r"/(news|economy|features)/20\d{2}/",
    ),
    HomepageHeadlineSite(
        "cbs",
        "Homepage: CBS News",
        "https://www.cbsnews.com/world/",
        ("https://www.cbsnews.com/",),
        r"/(news|world|politics|moneywatch|technology)/",
    ),
    HomepageHeadlineSite(
        "nbc",
        "Homepage: NBC News",
        "https://www.nbcnews.com/world",
        ("https://www.nbcnews.com/",),
        r"/world/",
    ),
)


class HomepageHeadlinesSource(NewsSource):
    """抓公開新聞首頁頭條；排程低頻跑，避免對來源站造成壓力。"""

    name = "homepage_headlines"

    def __init__(self, site_urls: list[str], timeout_seconds: int = 15) -> None:
        self.sites = [_site_for_url(url) for url in site_urls]
        self.timeout_seconds = timeout_seconds

    def fetch(self, limit: int = 20) -> list[NewsItem]:
        items: list[NewsItem] = []
        per_site_limit = max(int(limit), 1)

        for site in self.sites:
            fetched_at = datetime.now(timezone.utc)
            try:
                logger.info("Homepage headline request source=%s url=%s", site.source_id, site.url)
                html_text = http_get_text_with_headers(
                    site.url,
                    timeout=self.timeout_seconds,
                    headers={"Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8"},
                )
                rows = _parse_homepage_headlines(html_text, site)[:per_site_limit]
                logger.info("Homepage headline parsed source=%s items=%d", site.source_id, len(rows))
                items.extend(_row_to_item(row, site, fetched_at) for row in rows)
            except Exception as exc:  # pragma: no cover - network path
                logger.warning("Homepage headline failed source=%s url=%s error=%s", site.source_id, site.url, exc)

        return _dedupe(items)


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[_AnchorCandidate] = []
        self._stack: list[_OpenAnchor] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): value or "" for key, value in attrs}
        normalized_tag = tag.lower()
        if normalized_tag == "a":
            href = attr_map.get("href", "").strip()
            if href:
                seed = attr_map.get("aria-label", "") or attr_map.get("title", "")
                self._stack.append(_OpenAnchor(href=href, texts=[seed] if seed else []))

    def handle_data(self, data: str) -> None:
        if self._stack:
            self._stack[-1].texts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._stack:
            return
        anchor = self._stack.pop()
        title = _clean_text(" ".join(anchor.texts))
        if title:
            self.anchors.append(_AnchorCandidate(href=anchor.href, title=title))


def _parse_homepage_headlines(html_text: str, site: HomepageHeadlineSite) -> list[_AnchorCandidate]:
    parser = _AnchorParser()
    parser.feed(html_text)

    urls_in_order: list[str] = []
    rows_by_url: dict[str, _AnchorCandidate] = {}
    for anchor in parser.anchors:
        url = _canonical_url(anchor.href, site.url)
        title = _clean_headline(anchor.title, url)
        if not url or not title or not _is_article_url(url, site):
            continue
        current = rows_by_url.get(url)
        if current is None:
            urls_in_order.append(url)
            rows_by_url[url] = _AnchorCandidate(href=url, title=title)
        elif _headline_score(title) > _headline_score(current.title):
            rows_by_url[url] = _AnchorCandidate(href=url, title=title)
    return [rows_by_url[url] for url in urls_in_order]


def _row_to_item(row: _AnchorCandidate, site: HomepageHeadlineSite, fetched_at: datetime) -> NewsItem:
    return NewsItem(
        id=stable_id("homepage_headline", site.source_id, row.href),
        source=site.label,
        title=row.title,
        url=row.href,
        # 首頁通常沒有穩定發布時間；用抓取時間排序，raw 內保留來源語意。
        published_at=fetched_at,
        summary=None,
        tags=["english", "homepage_headline", "international"],
        raw={
            "kind": "homepage_headline",
            "source_id": site.source_id,
            "source_url": site.url,
            "published_at_source": "fetched_at_homepage_fallback",
            "fetched_at": fetched_at.isoformat(),
        },
    )


def _site_for_url(url: str) -> HomepageHeadlineSite:
    normalized = _normalize_home_url(url)
    for site in DEFAULT_HOMEPAGE_HEADLINE_SITES:
        if _normalize_home_url(site.url) == normalized:
            return site

    parsed = urlparse(url)
    for site in DEFAULT_HOMEPAGE_HEADLINE_SITES:
        if urlparse(site.url).netloc.lower() == parsed.netloc.lower():
            return HomepageHeadlineSite(site.source_id, site.label, url, site.article_prefixes, site.path_regex)

    host = parsed.netloc.lower().removeprefix("www.")
    source_id = re.sub(r"[^a-z0-9]+", "_", host).strip("_") or "custom"
    return HomepageHeadlineSite(
        source_id=source_id,
        label=f"Homepage: {host}",
        url=url,
        article_prefixes=(f"{parsed.scheme}://{parsed.netloc}/",),
        path_regex=r"/20\d{2}/|/article/",
    )


def _normalize_home_url(url: str) -> str:
    parsed = urlparse(url.strip())
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), "", "", ""))


def _canonical_url(href: str, base_url: str) -> str:
    joined = urljoin(base_url, unescape(href.strip()))
    parsed = urlparse(joined)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    query = urlencode(
        [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if not _TRACKING_PARAM_RE.search(key)]
    )
    return urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/") or "/", "", query, ""))


def _clean_headline(value: str, url: str = "") -> str:
    text = _clean_text(value)
    text = re.sub(r"^\d+\s*(?:h|hr|hrs|hour|hours|m|min|mins|minute|minutes)\s+ago\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+\d+\s*(?:h|hr|hrs|hour|hours|m|min|mins|minute|minutes)\s+ago\b.*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+\d+[hm]\s+ago\b.*$", "", text, flags=re.IGNORECASE)
    caption_tail = re.search(r"\b(?:19|20)\d{2}[.,]?\s+(.+)$", text)
    if caption_tail and (_CAPTION_PREFIX_RE.search(text) or _CAPTION_TERMS_RE.search(text) or len(text) > 140):
        tail_text = caption_tail.group(1).strip()
        text = _headline_from_url(url) if _CAPTION_TERMS_RE.search(tail_text) else tail_text
    elif _CAPTION_TERMS_RE.search(text):
        text = _headline_from_url(url) or text
    if len(text) > 100:
        tail = _SUMMARY_TAIL_RE.search(text, 40)
        if tail:
            text = text[: tail.start()].rstrip(" .")
    lowered = text.lower()
    if len(text) < 18 or len(text) > 220:
        return ""
    if lowered in _HEADLINE_BLOCKLIST:
        return ""
    if lowered.startswith(("• video", "live updates", "video ", "watch:")):
        return ""
    if any(blocked in lowered for blocked in (" sign up ", " subscribe ", " live tv ", " newsletter ")):
        return ""
    return text


def _clean_text(value: str) -> str:
    text = unescape(value)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" \t\r\n-|")


def _headline_score(title: str) -> int:
    lowered = title.lower()
    score = 120 - abs(len(title) - 85)
    if any(term in lowered for term in ("getty", "reuters", "ap photo", "image", "pictured", "caption")):
        score -= 80
    if len(title) > 150:
        score -= 30
    return score


def _headline_from_url(url: str) -> str:
    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    if "-" not in slug or re.fullmatch(r"[a-z]*\d+[a-z\d]*", slug, re.IGNORECASE):
        return ""

    words = [
        word
        for word in re.split(r"-+", slug)
        if word and word not in {"hnk", "intl", "latam"} and not re.fullmatch(r"rcna\d+", word, re.IGNORECASE)
    ]
    if len(words) < 4:
        return ""
    return " ".join(_format_slug_word(word) for word in words)


def _format_slug_word(word: str) -> str:
    upper_words = {"ai", "uk", "un", "us", "usa", "u.s"}
    return word.upper() if word.lower() in upper_words else word.capitalize()


def _is_article_url(url: str, site: HomepageHeadlineSite) -> bool:
    lowered = url.lower()
    if not any(lowered.startswith(prefix.lower()) for prefix in site.article_prefixes):
        return False
    path = urlparse(lowered).path
    if path.rstrip("/") in {"", "/news", "/world", "/world-news", "/international"}:
        return False
    if any(part in path for part in _DISALLOWED_PATH_PARTS):
        return False
    return re.search(site.path_regex, path) is not None


def _dedupe(items: list[NewsItem]) -> list[NewsItem]:
    seen: set[str] = set()
    result: list[NewsItem] = []
    for item in items:
        if item.url in seen:
            continue
        seen.add(item.url)
        result.append(item)
    return result
