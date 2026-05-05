"""HTTP entry points for the event relay.

Threaded ``http.server`` exposing ``GET /healthz``, ``POST /events``
(news/X/market_context ingest), ``POST /quote-snapshots`` (REQ-019 high-
frequency quote rows), ``POST /market-analysis/run`` (legacy daily analysis
trigger), and ``POST /analysis/backfill`` (operator-triggered daily / weekly
analysis backfill). Routes delegate to ``RelayProcessor`` in ``service.py``.
"""

from __future__ import annotations

# Event relay HTTP entrypoints for data ingestion.
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from typing import Any
from urllib.parse import urlsplit

from event_relay.service import RelayProcessor


logger = logging.getLogger(__name__)


_ALLOWED_MARKET_ANALYSIS_SLOTS = {"auto", "us_close", "pre_tw_open", "tw_close", "macro_daily"}
_ALLOWED_BACKFILL_KINDS = {"market", "weekly"}


class RelayHttpServer(ThreadingHTTPServer):
    """封裝 Relay Http Server 相關資料與行為。"""
    def __init__(
        self,
        server_address: tuple[str, int],
        processor: RelayProcessor,
        env_file: str = ".env",
    ) -> None:
        """初始化物件狀態與必要依賴。"""
        self.processor = processor
        self.env_file = env_file
        super().__init__(server_address, RelayRequestHandler)


class RelayRequestHandler(BaseHTTPRequestHandler):
    """封裝 Relay Request Handler 相關資料與行為。"""
    server: RelayHttpServer

    def do_GET(self) -> None:  # noqa: N802
        """執行 do G E T 方法的主要邏輯。"""
        if self._request_path() == "/healthz":
            self._json_response(200, {"ok": True})
            return
        self._json_response(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        """執行 do P O S T 方法的主要邏輯。"""
        path = self._request_path()

        if path == "/events":
            self._handle_events_post()
            return

        if path == "/quote-snapshots":
            self._handle_quote_snapshots_post()
            return

        if path == "/market-analysis/run":
            self._handle_market_analysis_run()
            return

        if path == "/analysis/backfill":
            self._handle_analysis_backfill()
            return

        self._json_response(404, {"error": "not_found"})

    def _handle_events_post(self) -> None:
        """處理 handle events post 對應的資料或結果。"""
        try:
            payload = self._read_json_body()
            result = self.server.processor.process_payload(payload)
            self._json_response(200, result)
        except ValueError as exc:
            self._json_response(400, {"error": str(exc)})
        except Exception as exc:
            logger.exception("Unhandled error while processing /events")
            self._json_response(500, {"error": str(exc)})

    def _handle_quote_snapshots_post(self) -> None:
        """處理 handle quote snapshots post 對應的資料或結果。"""
        try:
            payload = self._read_json_body()
            result = self.server.processor.process_quote_snapshots(payload)
            self._json_response(200, result)
        except ValueError as exc:
            self._json_response(400, {"error": str(exc)})
        except Exception as exc:
            logger.exception("Unhandled error while processing /quote-snapshots")
            self._json_response(500, {"error": str(exc)})

    def _handle_market_analysis_run(self) -> None:
        """處理 handle market analysis run 對應的資料或結果。"""
        try:
            payload = self._read_json_body_optional()
        except ValueError as exc:
            self._json_response(400, {"error": str(exc)})
            return

        slot = str(payload.get("slot") or "auto").strip().lower()
        if slot not in _ALLOWED_MARKET_ANALYSIS_SLOTS:
            self._json_response(
                400,
                {
                    "error": "invalid_slot",
                    "allowed": sorted(_ALLOWED_MARKET_ANALYSIS_SLOTS),
                },
            )
            return
        force = bool(payload.get("force", True))

        try:
            result = self._run_market_analysis(slot=slot, force=force)
            self._json_response(200, result)
        except RuntimeError as exc:
            logger.warning("/market-analysis/run failed: %s", exc)
            self._json_response(400, {"error": str(exc)})
        except Exception as exc:
            logger.exception("Unhandled error while running /market-analysis/run")
            self._json_response(500, {"error": str(exc)})

    def _handle_analysis_backfill(self) -> None:
        """Trigger daily or weekly analysis from curl / ops tools."""
        try:
            payload = self._read_json_body_optional()
        except ValueError as exc:
            self._json_response(400, {"error": str(exc)})
            return

        kind = self._coerce_backfill_kind(payload)
        if kind not in _ALLOWED_BACKFILL_KINDS:
            self._json_response(
                400,
                {
                    "error": "invalid_kind",
                    "allowed": sorted(_ALLOWED_BACKFILL_KINDS),
                },
            )
            return

        force = bool(payload.get("force", True))
        try:
            if kind == "weekly":
                result = self._run_weekly_summary(force=force)
            else:
                slot = str(payload.get("slot") or "auto").strip().lower()
                if slot not in _ALLOWED_MARKET_ANALYSIS_SLOTS:
                    self._json_response(
                        400,
                        {
                            "error": "invalid_slot",
                            "allowed": sorted(_ALLOWED_MARKET_ANALYSIS_SLOTS),
                        },
                    )
                    return
                result = self._run_market_analysis(slot=slot, force=force)
            self._json_response(200, {"ok": True, "kind": kind, "result": result})
        except RuntimeError as exc:
            logger.warning("/analysis/backfill failed kind=%s: %s", kind, exc)
            self._json_response(400, {"error": str(exc), "kind": kind})
        except Exception as exc:
            logger.exception("Unhandled error while running /analysis/backfill kind=%s", kind)
            self._json_response(500, {"error": str(exc), "kind": kind})

    @staticmethod
    def _coerce_backfill_kind(payload: dict[str, Any]) -> str:
        """Normalize caller-friendly aliases into a backfill kind."""
        raw = str(payload.get("kind") or payload.get("type") or payload.get("analysis_type") or "market")
        kind = raw.strip().lower().replace("-", "_")
        if kind in {"daily", "market_analysis", "market_analysis_run"}:
            return "market"
        if kind in {"weekly_summary", "weekly_tw_preopen"}:
            return "weekly"
        return kind

    def _run_market_analysis(self, *, slot: str, force: bool) -> dict[str, Any]:
        """Run the existing market-analysis single-shot path."""
        from argparse import Namespace
        from event_relay.market_analysis import _load_config, run_once

        config = _load_config(Namespace(env_file=self.server.env_file, force=force, slot=slot))
        return run_once(config)

    def _run_weekly_summary(self, *, force: bool) -> dict[str, Any]:
        """Run the existing weekly-summary single-shot path."""
        from argparse import Namespace
        from event_relay.weekly_summary import _load_weekly_config, run_once

        config = _load_weekly_config(Namespace(env_file=self.server.env_file, force=force, dry_run=False))
        return run_once(config)

    def log_message(self, fmt: str, *args: Any) -> None:
        """執行 log message 方法的主要邏輯。"""
        logger.info("%s - %s", self.client_address[0], fmt % args)

    def _request_path(self) -> str:
        """送出請求並處理回應 request path 對應的資料或結果。"""
        return urlsplit(self.path).path

    def _read_raw_body(self) -> bytes:
        """讀取 read raw body 對應的資料或結果。"""
        content_len = int(self.headers.get("Content-Length", "0"))
        if content_len <= 0:
            raise ValueError("empty request body")
        return self.rfile.read(content_len)

    def _read_json_body(self) -> Any:
        """讀取 read json body 對應的資料或結果。"""
        raw = self._read_raw_body()
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid json: {exc}") from exc

    def _read_json_body_optional(self) -> dict[str, Any]:
        """讀取 read json body optional 對應的資料或結果。"""
        content_len = int(self.headers.get("Content-Length", "0"))
        if content_len <= 0:
            return {}
        raw = self.rfile.read(content_len)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid json: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("body must be a JSON object")
        return parsed

    def _json_response(self, status: int, data: dict[str, Any]) -> None:
        """執行 json response 方法的主要邏輯。"""
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
