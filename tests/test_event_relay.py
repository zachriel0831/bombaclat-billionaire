from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from event_relay.config import RelaySettings, load_settings
from event_relay.service import MySqlEventStore, RelayEvent, RelayProcessor


class _FakeStore:
    """封裝 Fake Store 相關資料與行為。"""
    def __init__(self) -> None:
        """初始化物件狀態與必要依賴。"""
        self.users: dict[str, bool] = {}
        self.groups: dict[str, bool] = {}
        self.market_payloads: list[dict] = []
        self.dispatched: list[tuple[int, str, str | None]] = []
        self.retention_calls: list[int] = []

    def upsert_market_snapshot(self, payload: dict) -> int:
        """新增或更新 upsert market snapshot 對應的資料或結果。"""
        self.market_payloads.append(payload)
        snapshot = payload.get("market_snapshot") if isinstance(payload, dict) else None
        indexes = snapshot.get("indexes") if isinstance(snapshot, dict) else None
        return len(indexes) if isinstance(indexes, list) else 0

    def delete_events_older_than_days(self, keep_days: int) -> int:
        """刪除 delete events older than days 對應的資料或結果。"""
        return 0

    def delete_retention_older_than_days(self, keep_days: int) -> dict[str, int]:
        """刪除 delete retention older than days 對應的資料或結果。"""
        self.retention_calls.append(keep_days)
        return {"events": 2, "x_posts": 3}


def _build_settings() -> RelaySettings:
    """建立 build settings 對應的資料或結果。"""
    return RelaySettings(
        host="127.0.0.1",
        port=18090,
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
        mysql_event_embedding_table="t_event_embeddings",
        mysql_analysis_embedding_table="t_analysis_embeddings",
        mysql_trade_signal_table="t_trade_signals",
        mysql_signal_review_table="t_signal_reviews",
        mysql_signal_outcome_table="t_signal_outcomes",
        mysql_connect_timeout_seconds=5,
        retention_enabled=True,
        retention_keep_days=7,
    )


class _FixedDateTime(datetime):
    """封裝 Fixed Date Time 相關資料與行為。"""
    @classmethod
    def now(cls, tz=None):
        """執行 now 方法的主要邏輯。"""
        value = datetime(2026, 4, 20, 1, 0, 0, tzinfo=timezone.utc)
        return value.astimezone(tz) if tz is not None else value


class _FakeOperationalError(Exception):
    """Fake connector operational error for stale-connection tests."""


class _DeadConnection:
    """Connection object that behaves like an idle-disconnected MySQL handle."""

    def __init__(self) -> None:
        self.closed = False

    def ping(self, **_kwargs):
        raise _FakeOperationalError("MySQL Connection not available")

    def close(self) -> None:
        self.closed = True

    def cursor(self):
        raise AssertionError("stale connection cursor should not be used")


class _LiveConnection:
    """Connection object returned after reconnect."""

    def __init__(self) -> None:
        self.cursor_calls = 0

    def ping(self, **_kwargs):
        return None

    def cursor(self):
        self.cursor_calls += 1
        return "cursor"


class _ReconnectConnector:
    """Minimal mysql.connector replacement for reconnect unit tests."""

    IntegrityError = RuntimeError
    OperationalError = _FakeOperationalError
    InterfaceError = _FakeOperationalError

    def __init__(self, connection: _LiveConnection) -> None:
        self.connection = connection
        self.connect_calls = 0

    def connect(self, **_kwargs):
        self.connect_calls += 1
        return self.connection


class _MigrationConnection:
    """Fake connection used by event-table migration tests."""

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class _MigrationCursor:
    """Fake cursor that exposes legacy event table columns and indexes."""

    def __init__(self) -> None:
        self.executed: list[str] = []

    def execute(self, sql: str, _params=None) -> None:
        self.executed.append(sql)

    def fetchall(self):
        last_sql = self.executed[-1]
        if "information_schema.columns" in last_sql:
            return [
                ("id",),
                ("event_id",),
                ("is_pushed",),
                ("line_pushed_at",),
                ("line_push_status",),
                ("line_push_error",),
                ("created_at",),
            ]
        if "information_schema.statistics" in last_sql:
            return [("PRIMARY",), ("uq_event_hash",), ("idx_push_queue",)]
        return []


class LineEventRelayTests(unittest.TestCase):
    """封裝 Line Event Relay Tests 相關資料與行為。"""
    def test_load_relay_settings_storage_defaults_and_env(self) -> None:
        """測試 test load relay settings storage defaults and env 的預期行為。"""
        keys = [
            "RELAY_RETENTION_ENABLED",
            "RELAY_RETENTION_KEEP_DAYS",
        ]
        original = {key: os.environ.get(key) for key in keys}
        for key in keys:
            os.environ.pop(key, None)
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                empty_env = Path(tmp_dir) / ".env"
                empty_env.write_text("", encoding="utf-8")
                defaults = load_settings(str(empty_env))

                env_path = Path(tmp_dir) / ".env.retention"
                env_path.write_text(
                    "\n".join(
                        [
                            "RELAY_RETENTION_ENABLED=false",
                            "RELAY_RETENTION_KEEP_DAYS=14",
                        ]
                    ),
                    encoding="utf-8",
                )
                configured = load_settings(str(env_path))
        finally:
            for key, value in original.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.assertTrue(defaults.retention_enabled)
        self.assertEqual(defaults.retention_keep_days, 7)
        self.assertEqual(defaults.mysql_trade_signal_table, "t_trade_signals")
        self.assertEqual(defaults.mysql_signal_review_table, "t_signal_reviews")
        self.assertEqual(defaults.mysql_signal_outcome_table, "t_signal_outcomes")
        self.assertFalse(configured.retention_enabled)
        self.assertEqual(configured.retention_keep_days, 14)

    def test_market_context_event_hash_uses_event_id_not_title_url(self) -> None:
        """測試 test market context event hash uses event id not title url 的預期行為。"""
        first = RelayEvent(
            event_id="market-context-a",
            source="market_context:us_treasury",
            title="US Treasury 10Y 4.26 percent",
            url="https://home.treasury.gov/treasury-daily-interest-rate-xml-feed",
            summary="as_of=2026-04-20",
            published_at="2026-04-20T00:00:00",
            log_only=False,
            raw={},
        )
        second = first.__class__(**{**first.__dict__, "event_id": "market-context-b", "published_at": "2026-04-21T00:00:00"})

        self.assertNotEqual(MySqlEventStore._event_hash_for_event(first), MySqlEventStore._event_hash_for_event(second))

    def test_daily_retention_cleanup_uses_configured_keep_days_once_per_day(self) -> None:
        """測試 test daily retention cleanup uses configured keep days once per day 的預期行為。"""
        settings = _build_settings()
        processor = RelayProcessor(settings)
        fake_store = _FakeStore()
        processor._store = fake_store

        with patch("event_relay.service.datetime", _FixedDateTime):
            processor._run_daily_retention_cleanup_if_due()
            processor._run_daily_retention_cleanup_if_due()

        self.assertEqual(fake_store.retention_calls, [7])

    def test_daily_retention_cleanup_skips_when_disabled(self) -> None:
        """測試 test daily retention cleanup skips when disabled 的預期行為。"""
        settings = _build_settings()
        settings = settings.__class__(**{**settings.__dict__, "retention_enabled": False})
        processor = RelayProcessor(settings)
        fake_store = _FakeStore()
        processor._store = fake_store

        with patch("event_relay.service.datetime", _FixedDateTime):
            processor._run_daily_retention_cleanup_if_due()

        self.assertEqual(fake_store.retention_calls, [])

    def test_mysql_store_cursor_reconnects_stale_connection(self) -> None:
        """Stale idle MySQL connections should reconnect before cursor creation."""
        dead = _DeadConnection()
        live = _LiveConnection()
        connector = _ReconnectConnector(live)
        store = MySqlEventStore.__new__(MySqlEventStore)
        store._settings = _build_settings()
        store._connector = connector
        store._conn = dead

        cursor = store._cursor()

        self.assertEqual(cursor, "cursor")
        self.assertTrue(dead.closed)
        self.assertIs(store._conn, live)
        self.assertEqual(connector.connect_calls, 1)
        self.assertEqual(live.cursor_calls, 1)

    def test_event_table_migration_drops_legacy_line_delivery_columns(self) -> None:
        """t_relay_events should not keep old LINE delivery queue columns."""
        conn = _MigrationConnection()
        cur = _MigrationCursor()
        store = MySqlEventStore.__new__(MySqlEventStore)
        store._conn = conn
        store._event_table = "t_relay_events"

        store._migrate_event_delivery_columns(cur)

        statements = "\n".join(cur.executed)
        self.assertIn("DROP INDEX `idx_push_queue`", statements)
        self.assertIn("DROP COLUMN `is_pushed`", statements)
        self.assertIn("DROP COLUMN `line_pushed_at`", statements)
        self.assertIn("DROP COLUMN `line_push_status`", statements)
        self.assertIn("DROP COLUMN `line_push_error`", statements)
        self.assertIn("ADD INDEX `idx_event_created` (`created_at`)", statements)
        self.assertEqual(conn.commits, 1)
        self.assertEqual(conn.rollbacks, 0)

    def test_is_older_than_days_true(self) -> None:
        """測試 test is older than days true 的預期行為。"""
        now_local = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)
        self.assertTrue(RelayProcessor._is_older_than_days("2026-03-04T10:00:00+00:00", days=2, now_local=now_local))

    def test_is_older_than_days_false_for_recent_window(self) -> None:
        """測試 test is older than days false for recent window 的預期行為。"""
        now_local = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)
        self.assertFalse(RelayProcessor._is_older_than_days("2026-03-05T00:00:01+00:00", days=2, now_local=now_local))


if __name__ == "__main__":
    unittest.main()
