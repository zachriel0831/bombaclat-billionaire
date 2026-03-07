from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import html
import json
import logging
import re
import threading
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from line_event_relay.config import RelaySettings


logger = logging.getLogger(__name__)

BENZINGA_ALLOWED_URL_PREFIXES = (
    "https://www.benzinga.com/crypto/cryptocurrency/",
    "https://www.benzinga.com/news/topics/",
    "https://www.benzinga.com/markets/",
    "https://www.benzinga.com/news/politics",
)


@dataclass
class RelayEvent:
    event_id: str
    source: str
    title: str
    url: str
    summary: str
    published_at: str | None
    log_only: bool
    raw: dict[str, Any]


@dataclass
class QueuedEvent:
    row_id: int
    source: str
    title: str
    url: str
    summary: str
    published_at: str | None


class LinePushClient:
    endpoint = "https://api.line.me/v2/bot/message/push"

    def __init__(self, settings: RelaySettings) -> None:
        self._token = settings.line_channel_access_token

    def push_text(self, target_id: str, text: str) -> None:
        if not self._token:
            raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN is empty")

        payload = {
            "to": target_id,
            "messages": [{"type": "text", "text": text}],
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        req = Request(self.endpoint, data=body, method="POST")
        req.add_header("Authorization", f"Bearer {self._token}")
        req.add_header("Content-Type", "application/json")

        try:
            with urlopen(req, timeout=10) as resp:
                code = int(getattr(resp, "status", 0))
                if code != 200:
                    response_body = resp.read().decode("utf-8", errors="replace")
                    raise RuntimeError(f"LINE push failed status={code} body={response_body}")
        except HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
            raise RuntimeError(f"LINE push HTTPError status={exc.code} body={body_text}") from exc
        except URLError as exc:
            raise RuntimeError(f"LINE push URLError: {exc}") from exc


class MySqlEventStore:
    def __init__(self, settings: RelaySettings) -> None:
        self._settings = settings
        self._event_table = settings.mysql_event_table
        self._group_table = settings.mysql_group_table
        self._user_table = settings.mysql_user_table
        self._x_table = settings.mysql_x_table
        self._connector = self._import_mysql_connector()
        self._conn = None
        self._lock = threading.RLock()

    def initialize(self) -> None:
        self._create_database_if_needed()
        self._connect_database()
        self._create_tables_if_needed()
        self.repair_queue_state()

    def repair_queue_state(self) -> dict[str, int]:
        if self._conn is None:
            return {"fixed_pushed_flag": 0, "fixed_missing_pushed_at": 0}

        fix_pushed_flag_sql = (
            f"UPDATE {self._event_table} "
            "SET is_pushed=1, "
            "line_push_status=CASE "
            "WHEN line_push_status IS NULL OR line_push_status='queued' THEN 'repaired_pushed' "
            "ELSE line_push_status END "
            "WHERE is_pushed=0 AND line_pushed_at IS NOT NULL"
        )
        fix_missing_pushed_at_sql = (
            f"UPDATE {self._event_table} "
            "SET line_pushed_at=DATE_FORMAT(created_at, '%Y-%m-%dT%H:%i:%sZ'), "
            "line_push_status=CASE "
            "WHEN line_push_status IS NULL OR line_push_status='queued' THEN 'repaired_pushed' "
            "ELSE line_push_status END "
            "WHERE is_pushed=1 AND (line_pushed_at IS NULL OR line_pushed_at='')"
        )

        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(fix_pushed_flag_sql)
                fixed_pushed_flag = int(cur.rowcount or 0)
                cur.execute(fix_missing_pushed_at_sql)
                fixed_missing_pushed_at = int(cur.rowcount or 0)
                self._conn.commit()
            finally:
                cur.close()

        if fixed_pushed_flag or fixed_missing_pushed_at:
            logger.warning(
                "Queue state repaired: fixed_pushed_flag=%d fixed_missing_pushed_at=%d",
                fixed_pushed_flag,
                fixed_missing_pushed_at,
            )
        return {
            "fixed_pushed_flag": fixed_pushed_flag,
            "fixed_missing_pushed_at": fixed_missing_pushed_at,
        }

    def enqueue_event_if_new(self, event: RelayEvent) -> bool:
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")

        event_hash = self._event_hash(event.title, event.url)
        sql = (
            f"INSERT INTO {self._event_table} "
            "(event_id, source, title, url, summary, published_at, event_hash, raw_json, is_pushed, line_push_status) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0,'queued')"
        )
        values = (
            event.event_id,
            event.source,
            event.title,
            event.url,
            event.summary,
            event.published_at,
            event_hash,
            json.dumps(event.raw, ensure_ascii=False),
        )

        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(sql, values)
                if event.source.lower().startswith("x:"):
                    self._upsert_x_post(cur, event)
                self._conn.commit()
                return True
            except self._connector.IntegrityError:
                self._conn.rollback()
                return False
            finally:
                cur.close()

    def fetch_unpushed_events(self, limit: int) -> list[QueuedEvent]:
        if self._conn is None:
            return []

        sql = (
            f"SELECT id, source, title, url, summary, published_at "
            f"FROM {self._event_table} "
            "WHERE is_pushed=0 AND line_pushed_at IS NULL "
            "ORDER BY created_at ASC, id ASC "
            "LIMIT %s"
        )
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(sql, (max(limit, 1),))
                rows = cur.fetchall()
            finally:
                cur.close()

        events: list[QueuedEvent] = []
        for row in rows:
            events.append(
                QueuedEvent(
                    row_id=int(row[0]),
                    source=str(row[1]),
                    title=str(row[2]),
                    url=str(row[3]),
                    summary=str(row[4] or ""),
                    published_at=str(row[5]) if row[5] is not None else None,
                )
            )
        return events

    def list_active_group_ids(self) -> list[str]:
        return self._list_active_ids(self._group_table, "group_id")

    def list_active_user_ids(self) -> list[str]:
        return self._list_active_ids(self._user_table, "user_id")

    def list_active_test_user_ids(self) -> list[str]:
        if self._conn is None:
            return []

        sql = f"SELECT user_id FROM {self._user_table} WHERE active=1 AND test_account=1"
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(sql)
                rows = cur.fetchall()
            finally:
                cur.close()

        return [str(row[0]) for row in rows if row and row[0]]

    def upsert_group(self, group_id: str, test_account: bool = False, active: bool = True) -> None:
        if self._conn is None:
            return

        value = (group_id or "").strip()
        if not value:
            return

        sql = (
            f"INSERT INTO {self._group_table} (group_id, test_account, active) "
            "VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE "
            "test_account=GREATEST(test_account, VALUES(test_account)), "
            "active=VALUES(active), "
            "updated_at=CURRENT_TIMESTAMP"
        )
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(sql, (value, 1 if test_account else 0, 1 if active else 0))
                self._conn.commit()
            finally:
                cur.close()

    def upsert_user(self, user_id: str, test_account: bool = False, active: bool = True) -> None:
        if self._conn is None:
            return

        value = (user_id or "").strip()
        if not value:
            return

        sql = (
            f"INSERT INTO {self._user_table} (user_id, test_account, active) "
            "VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE "
            "test_account=GREATEST(test_account, VALUES(test_account)), "
            "active=VALUES(active), "
            "updated_at=CURRENT_TIMESTAMP"
        )
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(sql, (value, 1 if test_account else 0, 1 if active else 0))
                self._conn.commit()
            finally:
                cur.close()

    def mark_event_dispatched(self, row_id: int, status: str, error: str | None = None) -> None:
        if self._conn is None:
            return

        sql = (
            f"UPDATE {self._event_table} "
            "SET is_pushed=1, line_pushed_at=%s, line_push_status=%s, line_push_error=%s "
            "WHERE id=%s"
        )
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(
                    sql,
                    (
                        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        status,
                        error,
                        int(row_id),
                    ),
                )
                self._conn.commit()
            finally:
                cur.close()

    def mark_event_failed(self, row_id: int, error: str | None = None) -> None:
        if self._conn is None:
            return

        sql = (
            f"UPDATE {self._event_table} "
            "SET line_push_status=%s, line_push_error=%s "
            "WHERE id=%s"
        )
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(sql, ("failed", error, int(row_id)))
                self._conn.commit()
            finally:
                cur.close()

    def _list_active_ids(self, table_name: str, id_column: str) -> list[str]:
        if self._conn is None:
            return []

        sql = f"SELECT {id_column} FROM {table_name} WHERE active=1"
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(sql)
                rows = cur.fetchall()
            finally:
                cur.close()

        return [str(row[0]) for row in rows if row and row[0]]

    def _create_database_if_needed(self) -> None:
        conn = self._connector.connect(
            host=self._settings.mysql_host,
            port=self._settings.mysql_port,
            user=self._settings.mysql_user,
            password=self._settings.mysql_password,
            connection_timeout=self._settings.mysql_connect_timeout_seconds,
            autocommit=True,
        )
        try:
            cur = conn.cursor()
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{self._settings.mysql_database}` CHARACTER SET utf8mb4")
            cur.close()
        finally:
            conn.close()

    def _connect_database(self) -> None:
        self._conn = self._connector.connect(
            host=self._settings.mysql_host,
            port=self._settings.mysql_port,
            user=self._settings.mysql_user,
            password=self._settings.mysql_password,
            database=self._settings.mysql_database,
            connection_timeout=self._settings.mysql_connect_timeout_seconds,
            autocommit=False,
        )

    def _create_tables_if_needed(self) -> None:
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")

        ddl_event = f"""
        CREATE TABLE IF NOT EXISTS `{self._event_table}` (
          id BIGINT NOT NULL AUTO_INCREMENT,
          event_id VARCHAR(128) NULL,
          source VARCHAR(64) NOT NULL,
          title TEXT NOT NULL,
          url TEXT NOT NULL,
          summary TEXT NULL,
          published_at VARCHAR(64) NULL,
          event_hash CHAR(40) NOT NULL,
          raw_json JSON NULL,
          is_pushed TINYINT(1) NOT NULL DEFAULT 0,
          line_pushed_at VARCHAR(32) NULL,
          line_push_status VARCHAR(24) NULL,
          line_push_error TEXT NULL,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          UNIQUE KEY uq_event_hash (event_hash),
          KEY idx_push_queue (is_pushed, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
        ddl_group = f"""
        CREATE TABLE IF NOT EXISTS `{self._group_table}` (
          id BIGINT NOT NULL AUTO_INCREMENT,
          group_id VARCHAR(128) NOT NULL,
          test_account TINYINT(1) NOT NULL DEFAULT 0,
          active TINYINT(1) NOT NULL DEFAULT 1,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          UNIQUE KEY uq_group_id (group_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
        ddl_user = f"""
        CREATE TABLE IF NOT EXISTS `{self._user_table}` (
          id BIGINT NOT NULL AUTO_INCREMENT,
          user_id VARCHAR(128) NOT NULL,
          test_account TINYINT(1) NOT NULL DEFAULT 0,
          active TINYINT(1) NOT NULL DEFAULT 1,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          UNIQUE KEY uq_user_id (user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
        ddl_x = f"""
        CREATE TABLE IF NOT EXISTS `{self._x_table}` (
          id BIGINT NOT NULL AUTO_INCREMENT,
          tweet_id VARCHAR(32) NOT NULL,
          username VARCHAR(64) NOT NULL,
          user_id VARCHAR(64) NULL,
          source VARCHAR(64) NOT NULL,
          title TEXT NOT NULL,
          tweet_text TEXT NULL,
          tweet_url VARCHAR(512) NOT NULL,
          posted_at VARCHAR(64) NULL,
          lang VARCHAR(16) NULL,
          metrics_json JSON NULL,
          relay_event_id VARCHAR(128) NULL,
          raw_json JSON NULL,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          UNIQUE KEY uq_tweet_id (tweet_id),
          UNIQUE KEY uq_tweet_url (tweet_url),
          KEY idx_x_username_posted (username, posted_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """

        cur = self._conn.cursor()
        try:
            cur.execute(ddl_event)
            cur.execute(ddl_group)
            cur.execute(ddl_user)
            cur.execute(ddl_x)
            self._conn.commit()
        finally:
            cur.close()

    def _upsert_x_post(self, cur: Any, event: RelayEvent) -> None:
        # 將 X 貼文資料落地到專用表，便於後續做帳號/推文分析。
        tweet_obj = {}
        if isinstance(event.raw, dict):
            raw_tweet = event.raw.get("raw")
            if isinstance(raw_tweet, dict):
                maybe_tweet = raw_tweet.get("tweet")
                if isinstance(maybe_tweet, dict):
                    tweet_obj = maybe_tweet

        source = (event.source or "").strip().lower()
        username = source.split(":", 1)[1] if ":" in source else "unknown"
        tweet_id = str(tweet_obj.get("id") or event.event_id or "").strip()
        if tweet_id.startswith("x-"):
            tweet_id = tweet_id[2:]
        if not tweet_id:
            tweet_id = hashlib.sha1(event.url.encode("utf-8")).hexdigest()[:20]

        user_id = None
        if isinstance(event.raw, dict):
            raw_section = event.raw.get("raw")
            if isinstance(raw_section, dict):
                value = raw_section.get("user_id")
                if value is not None:
                    user_id = str(value)

        lang = str(tweet_obj.get("lang") or "").strip() or None
        text = str(tweet_obj.get("text") or event.summary or "").strip() or None
        metrics = tweet_obj.get("public_metrics") if isinstance(tweet_obj.get("public_metrics"), dict) else None

        sql = (
            f"INSERT INTO {self._x_table} "
            "(tweet_id, username, user_id, source, title, tweet_text, tweet_url, posted_at, lang, metrics_json, relay_event_id, raw_json) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE "
            "title=VALUES(title), "
            "tweet_text=VALUES(tweet_text), "
            "posted_at=VALUES(posted_at), "
            "lang=VALUES(lang), "
            "metrics_json=VALUES(metrics_json), "
            "relay_event_id=VALUES(relay_event_id), "
            "raw_json=VALUES(raw_json)"
        )

        cur.execute(
            sql,
            (
                tweet_id,
                username,
                user_id,
                event.source,
                event.title,
                text,
                event.url,
                event.published_at,
                lang,
                json.dumps(metrics, ensure_ascii=False) if metrics is not None else None,
                event.event_id or None,
                json.dumps(event.raw, ensure_ascii=False),
            ),
        )

    @staticmethod
    def _event_hash(title: str, url: str) -> str:
        key = f"{' '.join(title.split()).lower()}::{url.strip().lower()}"
        return hashlib.sha1(key.encode("utf-8")).hexdigest()

    @staticmethod
    def _import_mysql_connector():
        try:
            import mysql.connector  # type: ignore
        except Exception as exc:
            raise RuntimeError("mysql-connector-python is required. Run: pip install -e .") from exc
        return mysql.connector


class RelayProcessor:
    def __init__(self, settings: RelaySettings) -> None:
        self._settings = settings
        self._line_client = LinePushClient(settings)
        self._store = None
        self._stop_event = threading.Event()
        self._dispatch_thread = None

        if settings.mysql_enabled:
            self._store = MySqlEventStore(settings)
            self._store.initialize()
            logger.info(
                "MySQL ready: %s:%s/%s event_table=%s group_table=%s user_table=%s x_table=%s",
                settings.mysql_host,
                settings.mysql_port,
                settings.mysql_database,
                settings.mysql_event_table,
                settings.mysql_group_table,
                settings.mysql_user_table,
                settings.mysql_x_table,
            )
        else:
            logger.warning("MySQL storage disabled (LINE_RELAY_MYSQL_ENABLED=false)")

        self._start_dispatch_scheduler()

    def process_line_webhook(self, raw_body: bytes, signature: str | None) -> dict[str, Any]:
        # ?? LINE ???????HMAC-SHA256(raw body) + base64?
        self._verify_line_signature(raw_body, signature)
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid json: {exc}") from exc

        raw_events = payload.get("events") if isinstance(payload, dict) else None
        if raw_events is None:
            raw_events = []
        if not isinstance(raw_events, list):
            raise ValueError("invalid LINE webhook payload: events should be a list")

        user_states: dict[str, bool] = {}
        group_states: dict[str, bool] = {}
        group_ids: set[str] = set()

        for event in raw_events:
            if not isinstance(event, dict):
                continue
            source = event.get("source")
            if not isinstance(source, dict):
                continue

            event_type = str(event.get("type") or "").strip().lower()
            source_type = str(source.get("type") or "").strip().lower()
            user_id = str(source.get("userId") or "").strip()
            group_id = str(source.get("groupId") or "").strip()
            room_id = str(source.get("roomId") or "").strip()

            if user_id and user_id not in user_states:
                user_states[user_id] = True

            group_or_room_id = ""
            if group_id:
                group_or_room_id = group_id
            elif room_id:
                group_or_room_id = room_id
            if group_or_room_id:
                group_ids.add(group_or_room_id)
                if group_or_room_id not in group_states:
                    group_states[group_or_room_id] = True

            joined_user_ids: list[str] = []
            if event_type == "memberjoined":
                joined_obj = event.get("joined")
                if isinstance(joined_obj, dict):
                    members = joined_obj.get("members")
                    if isinstance(members, list):
                        for member in members:
                            if not isinstance(member, dict):
                                continue
                            joined_user_id = str(member.get("userId") or "").strip()
                            if not joined_user_id:
                                continue
                            joined_user_ids.append(joined_user_id)
                            user_states[joined_user_id] = True

            # Log group invite/join signals for fast group_id discovery.
            if event_type in {"join", "memberjoined"}:
                joined_id = group_id or room_id
                if joined_id:
                    group_states[joined_id] = True
                logger.info(
                    "[LINE_GROUP_JOIN] event_type=%s source_type=%s group_id=%s user_id=%s joined_user_ids=%s",
                    event_type or "-",
                    source_type or "-",
                    joined_id or "-",
                    user_id or "-",
                    ",".join(sorted(set(joined_user_ids))) if joined_user_ids else "-",
                )
            elif event_type == "leave":
                left_id = group_id or room_id
                if left_id:
                    group_states[left_id] = False
                logger.info(
                    "[LINE_GROUP_LEAVE] source_type=%s group_id=%s user_id=%s",
                    source_type or "-",
                    left_id or "-",
                    user_id or "-",
                )
            elif event_type == "unfollow":
                if user_id:
                    user_states[user_id] = False
                logger.info("[LINE_USER_UNFOLLOW] user_id=%s", user_id or "-")
            elif event_type == "follow":
                if user_id:
                    user_states[user_id] = True
                logger.info("[LINE_USER_FOLLOW] user_id=%s", user_id or "-")

        active_users = 0
        inactive_users = 0
        active_groups = 0
        inactive_groups = 0
        if self._store is None:
            logger.warning("LINE webhook received but MySQL store is disabled")
        else:
            for uid in sorted(user_states):
                is_active = bool(user_states[uid])
                self._store.upsert_user(uid, test_account=False, active=is_active)
                if is_active:
                    active_users += 1
                else:
                    inactive_users += 1

            for gid in sorted(group_states):
                is_active = bool(group_states[gid])
                self._store.upsert_group(gid, test_account=False, active=is_active)
                if is_active:
                    active_groups += 1
                else:
                    inactive_groups += 1

        logger.info(
            "LINE webhook processed: events=%d users=%d groups=%d active_users=%d inactive_users=%d active_groups=%d inactive_groups=%d",
            len(raw_events),
            len(user_states),
            len(group_ids),
            active_users,
            inactive_users,
            active_groups,
            inactive_groups,
        )
        return {
            "ok": True,
            "received": len(raw_events),
            "active_users": active_users,
            "inactive_users": inactive_users,
            "active_groups": active_groups,
            "inactive_groups": inactive_groups,
            "group_ids": sorted(group_ids),
        }

    def process_direct_push(self, payload: Any) -> dict[str, Any]:
        events = self._extract_direct_events(payload)
        if not events:
            raise ValueError("direct push payload has no valid events")

        target_users = self._resolve_direct_target_users()
        if not target_users:
            raise ValueError(
                "No direct user targets configured. Set LINE_DIRECT_TARGET_USER_IDS or mark test_account=1 users active."
            )

        sent = 0
        for event in events:
            text = self._build_direct_text(event)
            if not text:
                continue

            if self._settings.dispatch_dry_run:
                for user_id in target_users:
                    logger.info(
                        "[DRY_RUN_DIRECT_PUSH] user_id=%s source=%s title=%s",
                        user_id,
                        event.get("source", "direct"),
                        event.get("title", "-"),
                    )
                sent += len(target_users)
                continue

            for user_id in target_users:
                self._line_client.push_text(user_id, text)
                sent += 1

            logger.info(
                "[DIRECT_PUSH_SENT] users=%d source=%s title=%s",
                len(target_users),
                event.get("source", "direct"),
                event.get("title", "-"),
            )

        return {
            "received": len(events),
            "target_users": len(target_users),
            "pushed": sent,
            "dry_run": self._settings.dispatch_dry_run,
        }

    def process_payload(self, payload: Any) -> dict[str, Any]:
        events = self._extract_events(payload)
        queued = 0
        logged_only = 0
        duplicates = 0
        failed = 0
        results: list[dict[str, Any]] = []

        for event in events:
            try:
                if event.log_only:
                    logger.info(
                        "[LOG_ONLY_EVENT] source=%s id=%s title=%s url=%s",
                        event.source,
                        event.event_id or "-",
                        event.title,
                        event.url,
                    )
                    logged_only += 1
                    results.append({"status": "logged_only", "url": event.url, "title": event.title})
                    continue

                inserted = True
                if self._store is not None:
                    inserted = self._store.enqueue_event_if_new(event)

                if inserted:
                    queued += 1
                    results.append({"status": "queued", "url": event.url, "title": event.title})
                else:
                    duplicates += 1
                    results.append({"status": "duplicate", "url": event.url, "title": event.title})
            except Exception as exc:
                failed += 1
                logger.exception("Failed to enqueue event url=%s", event.url)
                results.append({"status": "failed", "url": event.url, "error": str(exc)})

        return {
            "received": len(events),
            "queued": queued,
            "logged_only": logged_only,
            "duplicates": duplicates,
            "failed": failed,
            "results": results,
        }

    def _start_dispatch_scheduler(self) -> None:
        if self._store is None:
            logger.warning("Dispatch scheduler disabled because MySQL store is unavailable")
            return

        self._dispatch_thread = threading.Thread(target=self._dispatch_loop, daemon=True, name="line-relay-dispatch")
        self._dispatch_thread.start()
        logger.info(
            "Dispatch scheduler started: interval=%ss batch=%d dry_run=%s",
            self._settings.dispatch_interval_seconds,
            self._settings.dispatch_batch_size,
            self._settings.dispatch_dry_run,
        )

    def _dispatch_loop(self) -> None:
        interval = max(self._settings.dispatch_interval_seconds, 1)
        while not self._stop_event.is_set():
            try:
                self.dispatch_once()
            except Exception:
                logger.exception("Dispatch loop error")
            self._stop_event.wait(interval)

    def dispatch_once(self) -> None:
        if self._store is None:
            return

        self._store.repair_queue_state()

        # Poll only unpushed rows from queue table.
        pending = self._store.fetch_unpushed_events(self._settings.dispatch_batch_size)
        if not pending:
            logger.info("Dispatch tick: no pending events")
            return

        groups = self._store.list_active_group_ids()
        users = self._store.list_active_user_ids()
        targets = [("group", gid) for gid in groups] + [("user", uid) for uid in users]
        if not targets and self._settings.line_target_group_id:
            targets.append(("group", self._settings.line_target_group_id))

        if not targets:
            logger.warning("Dispatch tick: no active groups/users, keep events pending")
            return

        for event in pending:
            if self._is_test_source(event.source):
                self._store.mark_event_dispatched(event.row_id, status="skipped_test_source", error=None)
                logger.info(
                    "Dispatch skip test source: event_id=%s source=%s title=%s",
                    event.row_id,
                    event.source,
                    event.title,
                )
                continue

            message = self._build_push_text(event)
            try:
                if self._settings.dispatch_dry_run:
                    for target_type, target_id in targets:
                        logger.info(
                            "[DRY_RUN_PUSH] target_type=%s target_id=%s event_id=%s title=%s url=%s",
                            target_type,
                            target_id,
                            event.row_id,
                            event.title,
                            event.url,
                        )
                    self._store.mark_event_dispatched(event.row_id, status="dry_run_logged", error=None)
                else:
                    for _, target_id in targets:
                        self._line_client.push_text(target_id, message)
                    self._store.mark_event_dispatched(event.row_id, status="pushed", error=None)
            except Exception as exc:
                self._store.mark_event_failed(event.row_id, error=str(exc))
                logger.exception("Dispatch failed event_id=%s", event.row_id)

    def _extract_events(self, payload: Any) -> list[RelayEvent]:
        if isinstance(payload, list):
            raw_events = payload
        elif isinstance(payload, dict) and isinstance(payload.get("events"), list):
            raw_events = payload["events"]
        elif isinstance(payload, dict):
            raw_events = [payload]
        else:
            raise ValueError("Unsupported payload: expected object, list, or {events:[...]}")

        events: list[RelayEvent] = []
        for obj in raw_events:
            if not isinstance(obj, dict):
                continue
            title = " ".join(str(obj.get("title") or "").split()).strip()
            url = str(obj.get("url") or "").strip()
            source = str(obj.get("source") or "unknown")
            published_at = str(obj.get("published_at") or "").strip() or None
            log_only = bool(obj.get("test_only")) or source.lower().startswith("manual_test")
            if not title or not url:
                continue
            if not self._allow_event_date(published_at):
                logger.debug(
                    "Drop stale event id=%s source=%s published_at=%s",
                    obj.get("id", "-"),
                    source,
                    published_at,
                )
                continue
            if source.lower().startswith("benzinga") and not self._allow_benzinga_url(url):
                logger.debug("Drop benzinga event by url rule id=%s url=%s", obj.get("id", "-"), url)
                continue

            events.append(
                RelayEvent(
                    event_id=str(obj.get("id") or ""),
                    source=source,
                    title=title,
                    url=url,
                    summary=self._normalize_summary(str(obj.get("summary") or "")),
                    published_at=published_at,
                    log_only=log_only,
                    raw=obj,
                )
            )

        return events

    @staticmethod
    def _extract_direct_events(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            raw_events = payload
        elif isinstance(payload, dict) and isinstance(payload.get("events"), list):
            raw_events = payload["events"]
        elif isinstance(payload, dict):
            raw_events = [payload]
        else:
            raise ValueError("Unsupported payload: expected object, list, or {events:[...]} for direct push")

        return [obj for obj in raw_events if isinstance(obj, dict)]

    def _resolve_direct_target_users(self) -> list[str]:
        from_env = [x.strip() for x in self._settings.line_direct_target_user_ids if x.strip()]
        if from_env:
            return sorted(set(from_env))

        if self._store is not None:
            test_users = self._store.list_active_test_user_ids()
            if test_users:
                return sorted(set(test_users))

        return []

    @staticmethod
    def _build_direct_text(event: dict[str, Any]) -> str:
        # direct push 允許多行格式，避免壓平成單行。
        text = str(event.get("text") or "").strip()
        if text:
            return text[:4500]

        title = " ".join(str(event.get("title") or "").split()).strip()
        url = str(event.get("url") or "").strip()
        if title and url:
            return f"{title}\n{url}"[:4500]
        if title:
            return title[:4500]
        return ""

    @staticmethod
    def _normalize_summary(value: str) -> str:
        text = html.unescape(value)
        text = re.sub(r"<[^>]+>", " ", text)
        text = " ".join(text.split())
        return text[:1200]

    def _verify_line_signature(self, raw_body: bytes, signature: str | None) -> None:
        secret = self._settings.line_channel_secret
        if not secret:
            raise ValueError("LINE_CHANNEL_SECRET is required for webhook verification")

        expected = base64.b64encode(hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()).decode(
            "utf-8"
        )
        incoming = (signature or "").strip()
        if not incoming or not hmac.compare_digest(expected, incoming):
            raise PermissionError("invalid LINE signature")

    @staticmethod
    def _build_push_text(event: QueuedEvent) -> str:
        # 依需求僅保留 title + url，避免把 summary/published_at 推進 LINE。
        title = " ".join((event.title or "").split()).strip()
        url = (event.url or "").strip()
        return f"{title}\n{url}".strip()[:4500]

    @staticmethod
    def _allow_benzinga_url(url: str) -> bool:
        check = (url or "").strip().lower()
        return any(check.startswith(prefix.lower()) for prefix in BENZINGA_ALLOWED_URL_PREFIXES)

    @staticmethod
    def _is_test_source(source: str | None) -> bool:
        value = (source or "").strip().lower()
        return value == "local_live_test" or value.startswith("manual_test")

    @staticmethod
    def _allow_event_date(published_at: str | None) -> bool:
        # Only keep events published today (local timezone) or future.
        if not published_at:
            return False
        parsed = RelayProcessor._parse_published_at(published_at)
        if parsed is None:
            return False
        today_local = datetime.now().astimezone().date()
        return parsed.date() >= today_local

    @staticmethod
    def _parse_published_at(value: str) -> datetime | None:
        normalized = value.strip().replace("Z", "+00:00")
        if not normalized:
            return None
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone()
