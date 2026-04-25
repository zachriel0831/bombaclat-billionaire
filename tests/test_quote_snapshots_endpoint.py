"""Tests for /quote-snapshots HTTP endpoint and RelayProcessor coercion."""
from __future__ import annotations

import json
import threading
import unittest
from http.client import HTTPConnection
from unittest.mock import MagicMock, patch

from event_relay.config import RelaySettings
from event_relay.http_server import RelayHttpServer
from event_relay.service import MarketQuoteSnapshot, RelayProcessor


def _settings() -> RelaySettings:
    return RelaySettings(
        host="127.0.0.1",
        port=0,
        dispatch_interval_seconds=300,
        mysql_enabled=False,
        mysql_host="127.0.0.1",
        mysql_port=3306,
        mysql_user="root",
        mysql_password="root",
        mysql_database="news_relay",
        mysql_event_table="t_relay_events",
        mysql_x_table="t_x_posts",
        mysql_market_table="t_market_index_snapshots",
        mysql_quote_snapshot_table="t_market_quote_snapshots",
        mysql_analysis_table="t_market_analyses",
        mysql_annotation_table="t_relay_event_annotations",
        mysql_connect_timeout_seconds=5,
        retention_enabled=False,
        retention_keep_days=7,
    )


class ProcessorCoerceTests(unittest.TestCase):
    def test_coerce_minimum_fields(self) -> None:
        snap = RelayProcessor._coerce_quote_snapshot(
            {
                "symbol": "2330.TW",
                "market": "TW",
                "ts": "2026-04-25 14:30:00",
                "price": 605.5,
            }
        )
        self.assertIsInstance(snap, MarketQuoteSnapshot)
        self.assertEqual(snap.symbol, "2330.TW")
        self.assertEqual(snap.market, "TW")
        self.assertEqual(snap.session, "regular")
        self.assertEqual(snap.close_price, 605.5)
        self.assertEqual(snap.source, "yfinance")

    def test_coerce_uses_open_high_low_aliases(self) -> None:
        snap = RelayProcessor._coerce_quote_snapshot(
            {
                "symbol": "AAPL",
                "market": "US",
                "ts": "2026-04-25 14:30:00",
                "open": 200.0,
                "high": 205.0,
                "low": 198.0,
                "close": 204.0,
                "volume": "100000",
                "raw_json": {"category": "us"},
            }
        )
        self.assertEqual(snap.open_price, 200.0)
        self.assertEqual(snap.high_price, 205.0)
        self.assertEqual(snap.low_price, 198.0)
        self.assertEqual(snap.close_price, 204.0)
        self.assertEqual(snap.volume, 100000)
        self.assertEqual(json.loads(snap.raw_json)["category"], "us")

    def test_coerce_rejects_missing_required(self) -> None:
        with self.assertRaises(ValueError):
            RelayProcessor._coerce_quote_snapshot({"symbol": "X", "market": "US"})


class ProcessorQuoteSnapshotsTests(unittest.TestCase):
    def setUp(self) -> None:
        # Bypass __init__ side-effects (DB, scheduler) — only test the method.
        self.proc = RelayProcessor.__new__(RelayProcessor)
        self.proc._settings = _settings()
        self.proc._store = MagicMock()
        self.proc._stop_event = threading.Event()
        self.proc._maintenance_thread = None
        self.proc._daily_cleanup_ran_for_date = None

    def test_stores_valid_rows_skips_invalid(self) -> None:
        result = self.proc.process_quote_snapshots(
            [
                {"symbol": "2330.TW", "market": "TW", "ts": "2026-04-25 14:30:00", "price": 605.5},
                {"symbol": "", "market": "TW", "ts": "2026-04-25 14:30:00"},  # invalid
                "not_an_object",  # invalid
            ]
        )
        self.assertEqual(result["received"], 3)
        self.assertEqual(result["stored"], 1)
        self.assertEqual(result["skipped"], 2)
        self.proc._store.upsert_market_quote_snapshot.assert_called_once()

    def test_dropped_when_store_disabled(self) -> None:
        self.proc._store = None
        result = self.proc.process_quote_snapshots(
            [{"symbol": "X", "market": "US", "ts": "2026-04-25 14:30:00"}]
        )
        self.assertEqual(result["stored"], 0)
        self.assertEqual(result["results"][0]["status"], "dropped")

    def test_failure_path_records_error(self) -> None:
        self.proc._store.upsert_market_quote_snapshot.side_effect = RuntimeError("boom")
        result = self.proc.process_quote_snapshots(
            [{"symbol": "X", "market": "US", "ts": "2026-04-25 14:30:00"}]
        )
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["results"][0]["status"], "failed")

    def test_payload_must_be_list(self) -> None:
        with self.assertRaises(ValueError):
            self.proc.process_quote_snapshots({"symbol": "X"})


class _FakeProcessor:
    def __init__(self) -> None:
        self.calls: list = []

    def process_quote_snapshots(self, payload):
        self.calls.append(payload)
        return {"received": len(payload), "stored": len(payload)}


def _start(processor) -> tuple[RelayHttpServer, threading.Thread]:
    server = RelayHttpServer(("127.0.0.1", 0), processor, env_file=".env")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _stop(server: RelayHttpServer, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2.0)


def _post(server: RelayHttpServer, body) -> tuple[int, dict]:
    conn = HTTPConnection(*server.server_address)
    try:
        raw = json.dumps(body).encode("utf-8")
        conn.request(
            "POST",
            "/quote-snapshots",
            body=raw,
            headers={"Content-Type": "application/json", "Content-Length": str(len(raw))},
        )
        resp = conn.getresponse()
        data = resp.read().decode("utf-8")
        return resp.status, json.loads(data) if data else {}
    finally:
        conn.close()


class QuoteSnapshotsEndpointTests(unittest.TestCase):
    def test_post_routes_to_processor(self) -> None:
        proc = _FakeProcessor()
        server, thread = _start(proc)
        try:
            status, body = _post(
                server,
                [{"symbol": "AAPL", "market": "US", "ts": "2026-04-25 14:30:00", "close": 200.0}],
            )
        finally:
            _stop(server, thread)
        self.assertEqual(status, 200)
        self.assertEqual(body["stored"], 1)
        self.assertEqual(len(proc.calls), 1)


if __name__ == "__main__":
    unittest.main()
