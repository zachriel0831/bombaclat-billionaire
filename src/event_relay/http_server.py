from __future__ import annotations

# Event relay HTTP entrypoints for data ingestion.
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from typing import Any
from urllib.parse import urlsplit

from event_relay.service import RelayProcessor


logger = logging.getLogger(__name__)


class RelayHttpServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        processor: RelayProcessor,
    ) -> None:
        self.processor = processor
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
