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
    """封裝 Fake Processor 相關資料與行為。"""
    def process_payload(self, payload: dict) -> dict:
        """執行 process payload 方法的主要邏輯。"""
        return {"ok": True, "processed": 0}


def _start_server() -> tuple[RelayHttpServer, threading.Thread]:
    """執行 start server 的主要流程。"""
    server = RelayHttpServer(("127.0.0.1", 0), _FakeProcessor(), env_file=".env")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _stop_server(server: RelayHttpServer, thread: threading.Thread) -> None:
    """執行 stop server 的主要流程。"""
    server.shutdown()
    server.server_close()
    thread.join(timeout=2.0)


def _post_json(server: RelayHttpServer, path: str, body: dict | None) -> tuple[int, dict]:
    """送出 post json 對應的資料或結果。"""
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
    """封裝 Market Analysis Endpoint Tests 相關資料與行為。"""
    def test_invalid_slot_returns_400(self) -> None:
        """測試 test invalid slot returns 400 的預期行為。"""
        server, thread = _start_server()
        try:
            status, body = _post_json(server, "/market-analysis/run", {"slot": "nonsense"})
        finally:
            _stop_server(server, thread)

        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "invalid_slot")
        self.assertIn("auto", body["allowed"])

    def test_happy_path_invokes_run_once_with_slot_and_force(self) -> None:
        """測試 test happy path invokes run once with slot and force 的預期行為。"""
        captured: dict = {}

        def fake_load_config(args):
            """執行 fake load config 方法的主要邏輯。"""
            captured["args"] = args
            return SimpleNamespace(slot=args.slot, force=args.force)

        def fake_run_once(config):
            """執行 fake run once 方法的主要邏輯。"""
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
        """測試 test empty body defaults to auto and force true 的預期行為。"""
        captured: dict = {}

        def fake_load_config(args):
            """執行 fake load config 方法的主要邏輯。"""
            captured["args"] = args
            return SimpleNamespace()

        def fake_run_once(_config):
            """執行 fake run once 方法的主要邏輯。"""
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
        """測試 test runtime error returns 400 的預期行為。"""
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

    def test_backfill_market_invokes_market_analysis(self) -> None:
        """測試 /analysis/backfill kind=market 會補日分析。"""
        captured: dict = {}

        def fake_load_config(args):
            captured["args"] = args
            return SimpleNamespace(slot=args.slot, force=args.force)

        def fake_run_once(config):
            captured["config"] = config
            return {"ok": True, "slot": config.slot}

        server, thread = _start_server()
        try:
            with patch("event_relay.market_analysis._load_config", side_effect=fake_load_config):
                with patch("event_relay.market_analysis.run_once", side_effect=fake_run_once):
                    status, body = _post_json(
                        server,
                        "/analysis/backfill",
                        {"kind": "market", "slot": "tw_close", "force": True},
                    )
        finally:
            _stop_server(server, thread)

        self.assertEqual(status, 200)
        self.assertEqual(body["kind"], "market")
        self.assertEqual(body["result"]["slot"], "tw_close")
        self.assertEqual(captured["args"].slot, "tw_close")
        self.assertTrue(captured["args"].force)

    def test_backfill_market_allows_macro_daily_slot(self) -> None:
        captured: dict = {}

        def fake_load_config(args):
            captured["args"] = args
            return SimpleNamespace(slot=args.slot, force=args.force)

        def fake_run_once(config):
            return {"ok": True, "slot": config.slot}

        server, thread = _start_server()
        try:
            with patch("event_relay.market_analysis._load_config", side_effect=fake_load_config):
                with patch("event_relay.market_analysis.run_once", side_effect=fake_run_once):
                    status, body = _post_json(
                        server,
                        "/analysis/backfill",
                        {"kind": "market", "slot": "macro_daily", "force": True},
                    )
        finally:
            _stop_server(server, thread)

        self.assertEqual(status, 200)
        self.assertEqual(body["result"]["slot"], "macro_daily")
        self.assertEqual(captured["args"].slot, "macro_daily")

    def test_backfill_weekly_invokes_weekly_summary(self) -> None:
        """測試 /analysis/backfill kind=weekly 會補週分析。"""
        captured: dict = {}

        def fake_load_weekly_config(args):
            captured["args"] = args
            return SimpleNamespace(force=args.force)

        def fake_run_once(config):
            captured["config"] = config
            return {"ok": True, "analysis_slot": "weekly_tw_preopen"}

        server, thread = _start_server()
        try:
            with patch("event_relay.weekly_summary._load_weekly_config", side_effect=fake_load_weekly_config):
                with patch("event_relay.weekly_summary.run_once", side_effect=fake_run_once):
                    status, body = _post_json(
                        server,
                        "/analysis/backfill",
                        {"kind": "weekly", "force": True},
                    )
        finally:
            _stop_server(server, thread)

        self.assertEqual(status, 200)
        self.assertEqual(body["kind"], "weekly")
        self.assertEqual(body["result"]["analysis_slot"], "weekly_tw_preopen")
        self.assertEqual(captured["args"].env_file, ".env")
        self.assertTrue(captured["args"].force)
        self.assertFalse(captured["args"].dry_run)

    def test_backfill_weekly_alias_supported(self) -> None:
        """測試 weekly_tw_preopen alias 可用。"""
        server, thread = _start_server()
        try:
            with patch("event_relay.weekly_summary._load_weekly_config", return_value=SimpleNamespace()):
                with patch("event_relay.weekly_summary.run_once", return_value={"ok": True}):
                    status, body = _post_json(
                        server,
                        "/analysis/backfill",
                        {"kind": "weekly_tw_preopen"},
                    )
        finally:
            _stop_server(server, thread)

        self.assertEqual(status, 200)
        self.assertEqual(body["kind"], "weekly")

    def test_backfill_invalid_kind_returns_400(self) -> None:
        """測試不支援的補分析種類會回 400。"""
        server, thread = _start_server()
        try:
            status, body = _post_json(server, "/analysis/backfill", {"kind": "unknown"})
        finally:
            _stop_server(server, thread)

        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "invalid_kind")

    def test_backfill_invalid_market_slot_returns_400(self) -> None:
        """測試 market 補分析 slot 驗證。"""
        server, thread = _start_server()
        try:
            status, body = _post_json(server, "/analysis/backfill", {"kind": "market", "slot": "weekly"})
        finally:
            _stop_server(server, thread)

        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "invalid_slot")


if __name__ == "__main__":
    unittest.main()
