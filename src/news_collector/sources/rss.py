from __future__ import annotations

import logging
from xml.etree import ElementTree as ET

from news_collector.http_client import http_get_text
from news_collector.models import NewsItem
from news_collector.sources.base import NewsSource
from news_collector.utils import local_name, parse_datetime, sort_timestamp, stable_id


logger = logging.getLogger(__name__)


class OfficialRssSource(NewsSource):
    name = "official_rss"

    def __init__(self, feed_urls: list[str], timeout_seconds: int = 15, first_per_feed: bool = False) -> None:
        self.feed_urls = feed_urls
        self.timeout_seconds = timeout_seconds
        self.first_per_feed = first_per_feed

    def fetch(self, limit: int = 20) -> list[NewsItem]:
        items: list[NewsItem] = []
        per_feed_limit = 1 if self.first_per_feed else max(int(limit), 1)
        for url in self.feed_urls:
            try:
                # 單一 feed 的請求與解析結果都會寫日誌，方便查來源是否失效。
                logger.info("RSS request feed=%s", url)
                xml_text = http_get_text(url, timeout=self.timeout_seconds)
                parsed = self._parse_feed(xml_text, url)
                parsed = parsed[:per_feed_limit]
                logger.info("RSS parsed feed=%s items=%d", url, len(parsed))
                items.extend(parsed)
            except Exception as exc:  # pragma: no cover - network path
                logger.warning("RSS failed feed=%s error=%s", url, exc)
                items.append(
                    NewsItem(
                        id=stable_id("rss-error", url),
                        source="official_rss:error",
                        title=f"Failed to fetch RSS: {url}",
                        url=url,
                        published_at=None,
                        summary=str(exc),
                        tags=["error"],
                        raw={"feed": url, "error": str(exc)},
                    )
                )

        deduped = self._dedupe(items)
        deduped.sort(key=lambda x: sort_timestamp(x.published_at), reverse=True)
        return deduped

    def _parse_feed(self, xml_text: str, feed_url: str) -> list[NewsItem]:
        root = ET.fromstring(xml_text)
        root_name = local_name(root.tag).lower()

        # 先判斷標準 RSS / Atom，降低後續節點掃描成本。
        if root_name == "rss":
            return self._parse_rss(root, feed_url)
        if root_name == "feed":
            return self._parse_atom(root, feed_url)

        # Fallback：對非標準格式嘗試抓 item / entry，提升相容性。
        nodes = root.findall(".//item") + root.findall(".//{*}entry")
        parsed: list[NewsItem] = []
        for node in nodes:
            parsed_item = self._node_to_item(node, feed_url, source_name="official_rss")
            if parsed_item:
                parsed.append(parsed_item)
        return parsed

    def _parse_rss(self, root: ET.Element, feed_url: str) -> list[NewsItem]:
        channel = root.find("channel")
        channel_title = (channel.findtext("title") if channel is not None else None) or "official_rss"
        items = root.findall(".//item")

        parsed: list[NewsItem] = []
        for node in items:
            news = self._node_to_item(node, feed_url, source_name=channel_title)
            if news:
                parsed.append(news)
        return parsed

    def _parse_atom(self, root: ET.Element, feed_url: str) -> list[NewsItem]:
        feed_title = root.findtext("{*}title") or "official_rss"
        entries = root.findall(".//{*}entry")

        parsed: list[NewsItem] = []
        for node in entries:
            news = self._node_to_item(node, feed_url, source_name=feed_title)
            if news:
                parsed.append(news)
        return parsed

    def _node_to_item(self, node: ET.Element, feed_url: str, source_name: str) -> NewsItem | None:
        def t(*names: str) -> str | None:
            for name in names:
                direct = node.findtext(name)
                if direct:
                    return direct.strip()
                for child in list(node):
                    if local_name(child.tag).lower() == name.lower() and (child.text or "").strip():
                        return child.text.strip()
            return None

        title = t("title")
        if not title:
            return None

        link = t("link")
        if not link:
            # Atom 常把連結放在 href 屬性而非文字節點。
            for child in list(node):
                if local_name(child.tag).lower() == "link":
                    href = child.attrib.get("href")
                    if href:
                        link = href
                        break

        if not link:
            link = feed_url

        published = parse_datetime(t("pubDate", "published", "updated"))
        summary = t("description", "summary", "content")

        tags: list[str] = []
        for child in list(node):
            name = local_name(child.tag).lower()
            if name == "category":
                term = (child.attrib.get("term") or child.text or "").strip()
                if term:
                    tags.append(term)

        return NewsItem(
            id=stable_id(source_name, title, link),
            source=source_name,
            title=title,
            url=link,
            published_at=published,
            summary=summary,
            tags=sorted(set(tags)),
            raw={"feed": feed_url},
        )

    @staticmethod
    def _dedupe(items: list[NewsItem]) -> list[NewsItem]:
        # RSS 內部先去重一次，避免同 feed 重複條目污染後續排序。
        seen: set[str] = set()
        result: list[NewsItem] = []
        for item in items:
            key = item.url or item.id
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result
