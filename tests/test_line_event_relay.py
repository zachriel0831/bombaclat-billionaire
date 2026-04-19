import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import unittest

from line_event_relay.config import RelaySettings
from line_event_relay.service import QueuedEvent, RelayProcessor


class _FakeStore:
    def __init__(self) -> None:
        self.users: dict[str, bool] = {}
        self.groups: dict[str, bool] = {}
        self.market_payloads: list[dict] = []
        self.pending_events: list[QueuedEvent] = []
        self.dispatched: list[tuple[int, str, str | None]] = []

    def upsert_user(self, user_id: str, test_account: bool = False, active: bool = True) -> None:
        self.users[user_id] = bool(active)

    def upsert_group(self, group_id: str, test_account: bool = False, active: bool = True) -> None:
        self.groups[group_id] = bool(active)

    def upsert_market_snapshot(self, payload: dict) -> int:
        self.market_payloads.append(payload)
        snapshot = payload.get("market_snapshot") if isinstance(payload, dict) else None
        indexes = snapshot.get("indexes") if isinstance(snapshot, dict) else None
        return len(indexes) if isinstance(indexes, list) else 0

    def repair_queue_state(self) -> dict[str, int]:
        return {"fixed_pushed_flag": 0, "fixed_missing_pushed_at": 0}

    def fetch_failed_event_for_retry(self):
        return None

    def fetch_unpushed_events(self, limit: int) -> list[QueuedEvent]:
        return list(self.pending_events[:limit])

    def list_active_group_ids(self) -> list[str]:
        return []

    def list_active_user_ids(self) -> list[str]:
        return ["U_ACTIVE"]

    def mark_event_dispatched(self, row_id: int, status: str, error: str | None = None) -> None:
        self.dispatched.append((row_id, status, error))

    def mark_event_failed(self, row_id: int, error: str | None = None) -> None:
        self.dispatched.append((row_id, "failed", error))

    def delete_events_older_than_days(self, keep_days: int) -> int:
        return 0


def _build_settings() -> RelaySettings:
    return RelaySettings(
        host="127.0.0.1",
        port=18090,
        line_channel_access_token="",
        line_channel_secret="unit-test-secret",
        line_target_group_id="",
        line_webhook_path="/line/webhook",
        line_direct_target_user_ids=["U_TEST_ONLY"],
        dispatch_interval_seconds=300,
        dispatch_batch_size=100,
        dispatch_dry_run=True,
        mysql_enabled=False,
        mysql_host="127.0.0.1",
        mysql_port=3306,
        mysql_user="root",
        mysql_password="root",
        mysql_database="news_relay",
        mysql_event_table="t_relay_events",
        mysql_group_table="t_bot_group_info",
        mysql_user_table="t_bot_user_info",
        mysql_x_table="t_x_posts",
        mysql_market_table="t_market_index_snapshots",
        mysql_connect_timeout_seconds=5,
    )


class LineEventRelayTests(unittest.TestCase):
    def test_build_push_text_only_title_and_url(self) -> None:
        event = QueuedEvent(
            row_id=1,
            source="bbc",
            title="Hello World",
            url="https://example.com/news",
            summary="should not appear",
            published_at="2026-03-07T00:00:00Z",
        )

        text = RelayProcessor._build_push_text(event)

        self.assertEqual(text, "Hello World\nhttps://example.com/news")

    def test_process_line_webhook_accepts_valid_signature(self) -> None:
        settings = _build_settings()
        processor = RelayProcessor(settings)
        body_obj = {
            "destination": "Uxxx",
            "events": [
                {"type": "follow", "source": {"type": "user", "userId": "U123"}},
                {"type": "join", "source": {"type": "group", "groupId": "C456", "userId": "U123"}},
            ],
        }
        raw_body = json.dumps(body_obj, ensure_ascii=False).encode("utf-8")
        signature = base64.b64encode(hmac.new(settings.line_channel_secret.encode("utf-8"), raw_body, hashlib.sha256).digest()).decode("utf-8")

        result = processor.process_line_webhook(raw_body, signature)

        self.assertTrue(result["ok"])
        self.assertEqual(result["received"], 2)
        self.assertIn("C456", result["group_ids"])

    def test_process_line_webhook_rejects_invalid_signature(self) -> None:
        settings = _build_settings()
        processor = RelayProcessor(settings)
        raw_body = b'{"events": []}'

        with self.assertRaises(PermissionError):
            processor.process_line_webhook(raw_body, "invalid-signature")

    def test_process_line_webhook_accepts_member_joined_event(self) -> None:
        settings = _build_settings()
        processor = RelayProcessor(settings)
        body_obj = {
            "destination": "Uxxx",
            "events": [
                {
                    "type": "memberJoined",
                    "source": {"type": "group", "groupId": "C777", "userId": "U_ADMIN"},
                    "joined": {"members": [{"type": "user", "userId": "U_JOINED"}]},
                }
            ],
        }
        raw_body = json.dumps(body_obj, ensure_ascii=False).encode("utf-8")
        signature = base64.b64encode(hmac.new(settings.line_channel_secret.encode("utf-8"), raw_body, hashlib.sha256).digest()).decode("utf-8")

        result = processor.process_line_webhook(raw_body, signature)

        self.assertTrue(result["ok"])
        self.assertEqual(result["received"], 1)
        self.assertIn("C777", result["group_ids"])

    def test_process_line_webhook_marks_group_inactive_on_leave(self) -> None:
        settings = _build_settings()
        processor = RelayProcessor(settings)
        fake_store = _FakeStore()
        processor._store = fake_store
        body_obj = {
            "destination": "Uxxx",
            "events": [
                {"type": "leave", "source": {"type": "group", "groupId": "C_LEAVE", "userId": "U_ADMIN"}},
            ],
        }
        raw_body = json.dumps(body_obj, ensure_ascii=False).encode("utf-8")
        signature = base64.b64encode(hmac.new(settings.line_channel_secret.encode("utf-8"), raw_body, hashlib.sha256).digest()).decode("utf-8")

        result = processor.process_line_webhook(raw_body, signature)

        self.assertTrue(result["ok"])
        self.assertEqual(fake_store.groups.get("C_LEAVE"), False)
        self.assertEqual(result["inactive_groups"], 1)

    def test_process_line_webhook_marks_user_inactive_on_unfollow(self) -> None:
        settings = _build_settings()
        processor = RelayProcessor(settings)
        fake_store = _FakeStore()
        processor._store = fake_store
        body_obj = {
            "destination": "Uxxx",
            "events": [
                {"type": "unfollow", "source": {"type": "user", "userId": "U_BLOCKED"}},
            ],
        }
        raw_body = json.dumps(body_obj, ensure_ascii=False).encode("utf-8")
        signature = base64.b64encode(hmac.new(settings.line_channel_secret.encode("utf-8"), raw_body, hashlib.sha256).digest()).decode("utf-8")

        result = processor.process_line_webhook(raw_body, signature)

        self.assertTrue(result["ok"])
        self.assertEqual(fake_store.users.get("U_BLOCKED"), False)
        self.assertEqual(result["inactive_users"], 1)

    def test_process_direct_push_dry_run_uses_direct_user_targets(self) -> None:
        settings = _build_settings()
        processor = RelayProcessor(settings)

        result = processor.process_direct_push(
            {
                "source": "us_index_tracker",
                "text": "[US_INDEX_OPEN] DJIA 47000.12 | S&P500 6100.34",
            }
        )

        self.assertEqual(result["received"], 1)
        self.assertEqual(result["target_users"], 1)
        self.assertEqual(result["pushed"], 1)
        self.assertEqual(result["recorded_market_rows"], 0)
        self.assertTrue(result["dry_run"])

    def test_process_direct_push_records_market_snapshot_rows(self) -> None:
        settings = _build_settings()
        processor = RelayProcessor(settings)
        fake_store = _FakeStore()
        processor._store = fake_store

        result = processor.process_direct_push(
            {
                "source": "us_index_tracker",
                "title": "US index close 2026-04-19",
                "text": "[US_INDEX_CLOSE] 2026-04-19",
                "event_id": "us_index_close_2026-04-19",
                "market_snapshot": {
                    "trade_date": "2026-04-19",
                    "session": "close",
                    "indexes": [
                        {
                            "symbol": "DJIA",
                            "label": "DJIA",
                            "url": "https://finance.yahoo.com/quote/%5EDJI",
                            "open_price": 40000.0,
                            "last_price": 40123.45,
                            "regular_start_epoch": 1,
                            "regular_end_epoch": 2,
                        },
                        {
                            "symbol": "S&P 500",
                            "label": "S&P 500",
                            "url": "https://finance.yahoo.com/quote/%5EGSPC",
                            "open_price": 5000.0,
                            "last_price": 5022.75,
                            "regular_start_epoch": 1,
                            "regular_end_epoch": 2,
                        },
                    ],
                },
            }
        )

        self.assertEqual(result["recorded_market_rows"], 2)
        self.assertEqual(len(fake_store.market_payloads), 1)

    def test_process_direct_push_requires_target(self) -> None:
        settings = _build_settings()
        settings = settings.__class__(**{**settings.__dict__, "line_direct_target_user_ids": []})
        processor = RelayProcessor(settings)

        with self.assertRaises(ValueError):
            processor.process_direct_push({"text": "hello"})

    def test_dispatch_once_marks_us_index_tracker_as_stored_only(self) -> None:
        settings = _build_settings()
        processor = RelayProcessor(settings)
        fake_store = _FakeStore()
        fake_store.pending_events = [
            QueuedEvent(
                row_id=99,
                source="us_index_tracker",
                title="US index close 2026-04-19",
                url="https://finance.yahoo.com/quote/%5EDJI",
                summary="close snapshot",
                published_at="2026-04-19T16:00:00Z",
            )
        ]
        processor._store = fake_store

        processor.dispatch_once()

        self.assertEqual(fake_store.dispatched, [(99, "stored_only_market", None)])

    def test_is_older_than_days_true(self) -> None:
        now_local = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)
        self.assertTrue(RelayProcessor._is_older_than_days("2026-03-04T10:00:00+00:00", days=2, now_local=now_local))

    def test_is_older_than_days_false_for_recent_window(self) -> None:
        now_local = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)
        self.assertFalse(RelayProcessor._is_older_than_days("2026-03-05T00:00:01+00:00", days=2, now_local=now_local))


if __name__ == "__main__":
    unittest.main()
