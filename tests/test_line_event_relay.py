import base64
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

    def upsert_user(self, user_id: str, test_account: bool = False, active: bool = True) -> None:
        self.users[user_id] = bool(active)

    def upsert_group(self, group_id: str, test_account: bool = False, active: bool = True) -> None:
        self.groups[group_id] = bool(active)


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
        self.assertTrue(result["dry_run"])

    def test_process_direct_push_requires_target(self) -> None:
        settings = _build_settings()
        settings = settings.__class__(**{**settings.__dict__, "line_direct_target_user_ids": []})
        processor = RelayProcessor(settings)

        with self.assertRaises(ValueError):
            processor.process_direct_push({"text": "hello"})


if __name__ == "__main__":
    unittest.main()
