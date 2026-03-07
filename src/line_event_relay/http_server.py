from __future__ import annotations

# 提供 relay HTTP 入口：/events 給資料橋接、/line/webhook 給 LINE 平台回呼。
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from typing import Any
from urllib.parse import urlsplit

from line_event_relay.service import RelayProcessor


logger = logging.getLogger(__name__)


class RelayHttpServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        processor: RelayProcessor,
        webhook_path: str = "/line/webhook",
    ) -> None:
        self.processor = processor
        normalized = (webhook_path or "/line/webhook").strip()
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        self.webhook_path = normalized
        super().__init__(server_address, RelayRequestHandler)


class RelayRequestHandler(BaseHTTPRequestHandler):
    server: RelayHttpServer

    def do_GET(self) -> None:  # noqa: N802
        if self._request_path() == "/healthz":
            self._json_response(200, {"ok": True})
            return
        self._json_response(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        path = self._request_path()

        if path == "/events":
            self._handle_events_post()
            return

        if path == self.server.webhook_path or path == "/callback":
            self._handle_line_webhook_post()
            return

        if path == "/push/direct":
            self._handle_direct_push_post()
            return

        self._json_response(404, {"error": "not_found"})

    def _handle_events_post(self) -> None:
        try:
            payload = self._read_json_body()
            result = self.server.processor.process_payload(payload)
            self._json_response(200, result)
        except ValueError as exc:
            self._json_response(400, {"error": str(exc)})
        except Exception as exc:
            logger.exception("Unhandled error while processing /events")
            self._json_response(500, {"error": str(exc)})

    def _handle_line_webhook_post(self) -> None:
        try:
            raw_body = self._read_raw_body()
            signature = self.headers.get("x-line-signature", "")
            result = self.server.processor.process_line_webhook(raw_body, signature)
            self._json_response(200, result)
        except PermissionError as exc:
            self._json_response(401, {"error": str(exc)})
        except ValueError as exc:
            self._json_response(400, {"error": str(exc)})
        except Exception as exc:
            logger.exception("Unhandled error while processing LINE webhook")
            self._json_response(500, {"error": str(exc)})

    def _handle_direct_push_post(self) -> None:
        try:
            payload = self._read_json_body()
            result = self.server.processor.process_direct_push(payload)
            self._json_response(200, result)
        except ValueError as exc:
            self._json_response(400, {"error": str(exc)})
        except Exception as exc:
            logger.exception("Unhandled error while processing direct push")
            self._json_response(500, {"error": str(exc)})

    def log_message(self, fmt: str, *args: Any) -> None:
        logger.info("%s - %s", self.client_address[0], fmt % args)

    def _request_path(self) -> str:
        return urlsplit(self.path).path

    def _read_raw_body(self) -> bytes:
        content_len = int(self.headers.get("Content-Length", "0"))
        if content_len <= 0:
            raise ValueError("empty request body")
        return self.rfile.read(content_len)

    def _read_json_body(self) -> Any:
        raw = self._read_raw_body()
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid json: {exc}") from exc

    def _json_response(self, status: int, data: dict[str, Any]) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
