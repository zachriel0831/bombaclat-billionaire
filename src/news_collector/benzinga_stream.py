from __future__ import annotations

# Benzinga WebSocket 串流封裝：負責連線、重連、語言過濾與事件正規化。
from dataclasses import dataclass
from datetime import datetime
import json
import logging
import random
import re
import time
from typing import Callable, Any
from urllib.parse import urlencode

from news_collector.utils import parse_datetime, stable_id


logger = logging.getLogger(__name__)


@dataclass
class StreamConfig:
    api_key: str
    tickers: list[str]
    channels: list[str]
    languages: list[str]
    timeout_seconds: int = 30
    reconnect_max_seconds: int = 60
    stop_on_429: bool = False


class BenzingaNewsStreamer:
    endpoint = "wss://api.benzinga.com/api/v1/news/stream"

    def __init__(self, config: StreamConfig) -> None:
        self.config = config
        self._websocket = _import_websocket_client()
        self._language_set = {x.strip().lower() for x in config.languages if x.strip()}

    def run(
        self,
        on_event: Callable[[dict[str, Any]], None],
        max_messages: int | None = None,
        duration_seconds: int | None = None,
    ) -> None:
        backoff_seconds = 1.0
        total_messages = 0
        started = time.monotonic()

        while True:
            if duration_seconds is not None and (time.monotonic() - started) >= duration_seconds:
                logger.info("Stream ended by duration limit: %ss", duration_seconds)
                return

            ws = None
            try:
                ws_url = self._build_ws_url()
                logger.info(
                    "Connecting Benzinga stream (tickers=%s channels=%s languages=%s)",
                    ",".join(self.config.tickers) or "-",
                    ",".join(self.config.channels) or "-",
                    ",".join(sorted(self._language_set)) or "all",
                )
                ws = self._websocket.create_connection(ws_url, timeout=self.config.timeout_seconds)
                backoff_seconds = 1.0
                logger.info("Benzinga stream connected")

                while True:
                    if duration_seconds is not None and (time.monotonic() - started) >= duration_seconds:
                        logger.info("Stream ended by duration limit: %ss", duration_seconds)
                        return

                    try:
                        raw = ws.recv()
                    except self._websocket.WebSocketTimeoutException:
                        ws.ping("keepalive")
                        continue

                    if raw is None or raw == "":
                        continue

                    normalized = self._normalize_event(raw)
                    if normalized is None:
                        continue

                    on_event(normalized)
                    total_messages += 1

                    if max_messages is not None and total_messages >= max_messages:
                        logger.info("Stream ended by max_messages=%d", max_messages)
                        return
            except KeyboardInterrupt:
                logger.info("Stream interrupted by user")
                return
            except Exception as exc:
                is_rate_limited = "429" in str(exc)
                if is_rate_limited and self.config.stop_on_429:
                    logger.warning("Stream stopped by BENZINGA_STOP_ON_429 after 429: %s", exc)
                    return

                if is_rate_limited:
                    backoff_seconds = max(backoff_seconds, 15.0)

                wait_seconds = min(backoff_seconds, float(self.config.reconnect_max_seconds))
                jitter = random.uniform(0.0, 0.6)
                logger.warning("Stream error: %s; reconnect in %.1fs", exc, wait_seconds + jitter)

                sleep_seconds = wait_seconds + jitter
                if duration_seconds is not None:
                    remaining = duration_seconds - (time.monotonic() - started)
                    if remaining <= 0:
                        logger.info("Stream ended by duration limit: %ss", duration_seconds)
                        return
                    sleep_seconds = min(sleep_seconds, remaining)

                time.sleep(sleep_seconds)
                backoff_seconds = min(backoff_seconds * 2.0, float(self.config.reconnect_max_seconds))
            finally:
                if ws is not None:
                    try:
                        ws.close()
                    except Exception:
                        pass

    def _build_ws_url(self) -> str:
        params: dict[str, str] = {"token": self.config.api_key}
        if self.config.tickers:
            params["tickers"] = ",".join(self.config.tickers)
        if self.config.channels:
            params["channels"] = ",".join(self.config.channels)
        return f"{self.endpoint}?{urlencode(params)}"

    def _normalize_event(self, raw: str) -> dict[str, Any] | None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None

        payload = data.get("data", data) if isinstance(data, dict) else {}
        content = payload.get("content", payload) if isinstance(payload, dict) else {}

        title = _pick_first(content, ["title", "headline"]) or "(untitled)"
        url = _pick_first(content, ["url", "link"]) or ""
        published = _parse_stream_timestamp(payload, content)
        language = _infer_language(content, title)

        if self._language_set and language not in self._language_set:
            return None

        tags: list[str] = []
        for stock in content.get("stocks", []) if isinstance(content, dict) else []:
            if isinstance(stock, str):
                tags.append(stock)
            elif isinstance(stock, dict):
                symbol = stock.get("name") or stock.get("symbol")
                if symbol:
                    tags.append(str(symbol))

        for channel in content.get("channels", []) if isinstance(content, dict) else []:
            if isinstance(channel, str):
                tags.append(channel)
            elif isinstance(channel, dict):
                name = channel.get("name") or channel.get("slug")
                if name:
                    tags.append(str(name))

        item_id = str(
            payload.get("id")
            or data.get("id")
            or stable_id("benzinga_stream", title, url, str(published.isoformat() if published else ""))
        )

        return {
            "id": item_id,
            "source": "benzinga_stream",
            "title": title,
            "url": url,
            "published_at": published.isoformat() if published else None,
            "summary": _pick_first(content, ["teaser", "body"]),
            "tags": sorted(set(tags + [f"lang:{language}"])),
            "raw": data,
        }


def _pick_first(obj: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = obj.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _parse_stream_timestamp(payload: dict[str, Any], content: dict[str, Any]) -> datetime | None:
    candidates = [
        payload.get("timestamp"),
        content.get("created"),
        content.get("updated"),
        content.get("published"),
        content.get("date"),
        content.get("created_at"),
        content.get("updated_at"),
    ]
    for candidate in candidates:
        parsed = parse_datetime(str(candidate) if candidate is not None else None)
        if parsed is not None:
            return parsed
    return None


def _infer_language(content: dict[str, Any], title: str) -> str:
    content_type = str(content.get("type") or "").lower()

    mapped = _map_type_to_language(content_type)
    if mapped:
        return mapped

    if re.search(r"[\uac00-\ud7af]", title):
        return "ko"
    if re.search(r"[\u3040-\u30ff]", title):
        return "ja"
    if re.search(r"[\u4e00-\u9fff]", title):
        return "zh"
    if re.search(r"[\u0600-\u06ff]", title):
        return "ar"
    if re.search(r"[\u0400-\u04ff]", title):
        return "ru"

    return "en"


def _map_type_to_language(content_type: str) -> str | None:
    type_map = {
        "korea": "ko",
        "japan": "ja",
        "espanol": "es",
        "spanish": "es",
        "italia": "it",
        "italian": "it",
        "france": "fr",
        "french": "fr",
        "deutsch": "de",
        "german": "de",
        "china": "zh",
        "arabic": "ar",
    }
    for token, language in type_map.items():
        if token in content_type:
            return language

    if content_type and ("wire" in content_type or "slideshow" in content_type):
        return "en"
    return None


def _import_websocket_client():
    try:
        import websocket  # type: ignore
    except Exception as exc:
        raise RuntimeError("websocket-client package is required. Install with: pip install websocket-client") from exc
    return websocket
