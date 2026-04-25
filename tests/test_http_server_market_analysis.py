"""Tests for the /market-analysis/run HTTP endpoint."""
from __future__ import annotations

import json
import threading
import unittest
from http.client import HTTPConnection
from types import SimpleNamespace
from unittest.mock import patch

from event_relay.http_server import RelayHttpServer


class _FakeProcessor:
    def process_payload(self, payload: dict) -> dict:
        return {"ok": True, "processed": 0}


def _start_server() -> tuple[RelayHttpServer, threading.Thread]:
    server = RelayHttpServer(("127.0.0.1", 0), _FakeProcessor(), env_file=".env")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _stop_server(server: RelayHttpServer, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2.0)


def _post_json(server: RelayHttpServer, path: str, body: dict | None) -> tuple[int, dict]:
    conn = HTTPConnection(*server.server_address)
    try:
        payload = json.dumps(body).encode("utf-8") if body is not None else b""
        headers = {"Content-Type": "application/json"}
        if payload:
            headers["Content-Length"] = str(len(payload))
        conn.request("POST", path, body=payload, headers=headers)
        resp = conn.getresponse()
        data = resp.read().decode("utf-8")
        return resp.status, json.loads(data) if data else {}
    finally:
        conn.close()


class MarketAnalysisEndpointTests(unittest.TestCase):
    def test_invalid_slot_returns_400(self) -> None:
        server, thread = _start_server()
        try:
            status, body = _post_json(server, "/market-analysis/run", {"slot": "nonsense"})
        finally:
            _stop_server(server, thread)

        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "invalid_slot")
        self.assertIn("auto", body["allowed"])

    def test_happy_path_invokes_run_once_with_slot_and_force(self) -> None:
        captured: dict = {}

        def fake_load_config(args):
            captured["args"] = args
            return SimpleNamespace(slot=args.slot, force=args.force)

        def fake_run_once(config):
            captured["config"] = config
            return {
                "ok": True,
                "slot": "pre_tw_open",
                "analysis_date": "2026-04-22",
                "events_used": 5,
                "market_rows_used": 2,
                "push_enabled": True,
                "pushed": 0,
                "model": "test-model",
            }

        server, thread = _start_server()
        try:
            with patch("event_relay.market_analysis._load_config", side_effect=fake_load_config):
                with patch("event_relay.market_analysis.run_once", side_effect=fake_run_once):
                    status, body = _post_json(
                        server,
                        "/market-analysis/run",
                        {"slot": "pre_tw_open", "force": True},
                    )
        finally:
            _stop_server(server, thread)

        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["slot"], "pre_tw_open")
        self.assertEqual(captured["args"].slot, "pre_tw_open")
        self.assertTrue(captured["args"].force)
        self.assertEqual(captured["args"].env_file, ".env")

    def test_empty_body_defaults_to_auto_and_force_true(self) -> None:
        captured: dict = {}

        def fake_load_config(args):
            captured["args"] = args
            return SimpleNamespace()

        def fake_run_once(_config):
            return {"ok": True, "slot": "pre_tw_open"}

        server, thread = _start_server()
        try:
            with patch("event_relay.market_analysis._load_config", side_effect=fake_load_config):
                with patch("event_relay.market_analysis.run_once", side_effect=fake_run_once):
                    status, _ = _post_json(server, "/market-analysis/run", None)
        finally:
            _stop_server(server, thread)

        self.assertEqual(status, 200)
        self.assertEqual(captured["args"].slot, "auto")
        self.assertTrue(captured["args"].force)

    def test_runtime_error_returns_400(self) -> None:
        server, thread = _start_server()
        try:
            with patch(
                "event_relay.market_analysis._load_config",
                side_effect=RuntimeError("Missing openai API key. Checked env vars and file: .secrets/x.dpapi"),
            ):
                status, body = _post_json(server, "/market-analysis/run", {})
        finally:
            _stop_server(server, thread)

        self.assertEqual(status, 400)
        self.assertIn("Missing openai API key", body["error"])


if __name__ == "__main__":
    unittest.main()
