from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import html
import json
import logging
import re
import threading
from typing import Any

from event_relay.config import RelaySettings


logger = logging.getLogger(__name__)


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
class SummaryEvent:
    row_id: int
    source: str
    title: str
    url: str
    summary: str
    published_at: str | None
    created_at: str
    raw_json: str | None = None


@dataclass
class MarketSnapshotRow:
    event_id: str
    source: str
    trade_date: str
    market_session: str
    symbol: str
    label: str
    quote_url: str | None
    open_price: float | None
    last_price: float | None
    recorded_price: float | None
    created_at: str


@dataclass
class MarketAnalysisRecord:
    analysis_date: str
    analysis_slot: str
    scheduled_time_local: str
    model: str
    prompt_version: str
    summary_text: str
    events_used: int
    market_rows_used: int
    push_enabled: bool
    pushed: bool
    raw_json: str | None = None
    structured_json: str | None = None


@dataclass
class StoredMarketAnalysisRecord:
    row_id: int
    analysis_date: str
    analysis_slot: str
    scheduled_time_local: str
    model: str
    prompt_version: str
    summary_text: str
    raw_json: str | None
    updated_at: str


class MySqlEventStore:
    def __init__(self, settings: RelaySettings) -> None:
        self._settings = settings
        self._event_table = settings.mysql_event_table
        self._x_table = settings.mysql_x_table
        self._market_table = settings.mysql_market_table
        self._analysis_table = settings.mysql_analysis_table
        self._annotation_table = settings.mysql_annotation_table
        self._connector = self._import_mysql_connector()
        self._conn = None
        self._lock = threading.RLock()

    def initialize(self) -> None:
        self._create_database_if_needed()
        self._connect_database()
        self._create_tables_if_needed()

    def enqueue_event_if_new(self, event: RelayEvent) -> bool:
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")

        event_hash = self._event_hash_for_event(event)
        sql = (
            f"INSERT INTO {self._event_table} "
            "(event_id, source, title, url, summary, published_at, event_hash, raw_json, is_pushed) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
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
            1,
        )

        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(sql, values)
                if event.source.lower().startswith("x:"):
                    self._upsert_x_post(cur, event)
                if self._has_market_snapshot(event):
                    self._upsert_market_snapshot_from_event(cur, event)
                self._conn.commit()
                return True
            except self._connector.IntegrityError:
                self._conn.rollback()
                return False
            finally:
                cur.close()

    def fetch_recent_summary_events(self, days: int, limit: int) -> list[SummaryEvent]:
        if self._conn is None:
            return []

        safe_days = max(int(days), 1)
        safe_limit = max(int(limit), 1)
        # Use the auto-increment primary key as the recency order. Recent
        # market-context rows can carry large official payloads, and filesort
        # over created_at/raw_json can exceed MySQL's sort buffer on small DBs.
        sql = (
            f"SELECT id, source, title, url, summary, published_at, created_at, raw_json "
            f"FROM {self._event_table} "
            "WHERE created_at >= (NOW() - INTERVAL %s DAY) "
            "AND source NOT REGEXP '^(local_live_test|manual_test)' "
            "ORDER BY id DESC "
            "LIMIT %s"
        )
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(sql, (safe_days, safe_limit))
                rows = cur.fetchall()
            finally:
                cur.close()

        result: list[SummaryEvent] = []
        for row in rows:
            result.append(
                SummaryEvent(
                    row_id=int(row[0]),
                    source=str(row[1]),
                    title=str(row[2]),
                    url=str(row[3]),
                    summary=str(row[4] or ""),
                    published_at=str(row[5]) if row[5] is not None else None,
                    created_at=str(row[6]),
                    raw_json=str(row[7]) if row[7] is not None else None,
                )
            )
        return result

    def fetch_event_annotations(self, event_row_ids: list[int]) -> dict[int, dict[str, Any]]:
        """Return stored annotations for the given event primary keys.

        Keys in the returned mapping match ``t_relay_events.id``. Rows without
        an annotation are simply absent — callers decide whether to fall back
        to an in-memory rule-based annotation.
        """
        if self._conn is None or not event_row_ids:
            return {}

        unique_ids = sorted({int(row_id) for row_id in event_row_ids if row_id is not None})
        if not unique_ids:
            return {}

        placeholders = ",".join(["%s"] * len(unique_ids))
        sql = (
            f"SELECT event_row_id, entities, category, importance, sentiment, "
            f"annotator, annotator_version, annotated_at "
            f"FROM {self._annotation_table} "
            f"WHERE event_row_id IN ({placeholders})"
        )
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(sql, tuple(unique_ids))
                rows = cur.fetchall()
            finally:
                cur.close()

        result: dict[int, dict[str, Any]] = {}
        for row in rows:
            entities_raw = row[1]
            try:
                entities = json.loads(entities_raw) if isinstance(entities_raw, str) else entities_raw
            except (ValueError, TypeError):
                entities = []
            if not isinstance(entities, list):
                entities = []
            result[int(row[0])] = {
                "entities": entities,
                "category": str(row[2] or "other"),
                "importance": float(row[3] or 0.0),
                "sentiment": str(row[4] or "neutral"),
                "annotator": str(row[5] or ""),
                "annotator_version": str(row[6] or ""),
                "annotated_at": str(row[7]) if row[7] is not None else "",
            }
        return result

    def upsert_event_annotation(
        self,
        event_row_id: int,
        *,
        entities: list[dict[str, str]],
        category: str,
        importance: float,
        sentiment: str,
        annotator: str,
        annotator_version: str,
    ) -> None:
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")

        sql = (
            f"INSERT INTO {self._annotation_table} "
            "(event_row_id, entities, category, importance, sentiment, annotator, annotator_version) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE "
            "entities=VALUES(entities), "
            "category=VALUES(category), "
            "importance=VALUES(importance), "
            "sentiment=VALUES(sentiment), "
            "annotator=VALUES(annotator), "
            "annotator_version=VALUES(annotator_version)"
        )
        values = (
            int(event_row_id),
            json.dumps(list(entities), ensure_ascii=False),
            str(category),
            float(importance),
            str(sentiment),
            str(annotator),
            str(annotator_version),
        )
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(sql, values)
                self._conn.commit()
            finally:
                cur.close()

    def fetch_recent_market_snapshots(self, hours: int, limit: int) -> list[MarketSnapshotRow]:
        if self._conn is None:
            return []

        safe_hours = max(int(hours), 1)
        safe_limit = max(int(limit), 1)
        sql = (
            f"SELECT event_id, source, trade_date, market_session, symbol, label, quote_url, "
            "open_price, last_price, recorded_price, created_at "
            f"FROM {self._market_table} "
            "WHERE created_at >= (NOW() - INTERVAL %s HOUR) "
            "ORDER BY created_at DESC, id DESC "
            "LIMIT %s"
        )
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(sql, (safe_hours, safe_limit))
                rows = cur.fetchall()
            finally:
                cur.close()

        result: list[MarketSnapshotRow] = []
        for row in rows:
            result.append(
                MarketSnapshotRow(
                    event_id=str(row[0] or ""),
                    source=str(row[1] or ""),
                    trade_date=str(row[2] or ""),
                    market_session=str(row[3] or ""),
                    symbol=str(row[4] or ""),
                    label=str(row[5] or ""),
                    quote_url=str(row[6]) if row[6] is not None else None,
                    open_price=self._to_decimal_value(row[7]),
                    last_price=self._to_decimal_value(row[8]),
                    recorded_price=self._to_decimal_value(row[9]),
                    created_at=str(row[10]) if row[10] is not None else "",
                )
            )
        return result

    def _migrate_analysis_structured_json(self, cur: Any) -> None:
        """Add structured_json column on existing deployments where DDL was already applied.

        Idempotent: silently skips when the column already exists.
        """
        if self._conn is None:
            return
        try:
            cur.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = 'structured_json' "
                "LIMIT 1",
                (self._analysis_table,),
            )
            exists = cur.fetchone() is not None
        except Exception:  # noqa: BLE001
            return
        if exists:
            return
        try:
            cur.execute(f"ALTER TABLE `{self._analysis_table}` ADD COLUMN structured_json JSON NULL AFTER raw_json")
            self._conn.commit()
        except Exception:  # noqa: BLE001
            # Column may have been added between our check and the ALTER; do not fail init.
            self._conn.rollback()

    def upsert_market_analysis(self, record: MarketAnalysisRecord) -> None:
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")

        sql = (
            f"INSERT INTO {self._analysis_table} "
            "(analysis_date, analysis_slot, scheduled_time_local, model, prompt_version, summary_text, "
            "events_used, market_rows_used, push_enabled, pushed, raw_json, structured_json) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE "
            "scheduled_time_local=VALUES(scheduled_time_local), "
            "model=VALUES(model), "
            "prompt_version=VALUES(prompt_version), "
            "summary_text=VALUES(summary_text), "
            "events_used=VALUES(events_used), "
            "market_rows_used=VALUES(market_rows_used), "
            "push_enabled=VALUES(push_enabled), "
            "pushed=VALUES(pushed), "
            "raw_json=VALUES(raw_json), "
            "structured_json=VALUES(structured_json), "
            "updated_at=CURRENT_TIMESTAMP"
        )

        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(
                    sql,
                    (
                        record.analysis_date,
                        record.analysis_slot,
                        record.scheduled_time_local,
                        record.model,
                        record.prompt_version,
                        record.summary_text,
                        record.events_used,
                        record.market_rows_used,
                        1 if record.push_enabled else 0,
                        1 if record.pushed else 0,
                        record.raw_json,
                        record.structured_json,
                    ),
                )
                self._conn.commit()
            finally:
                cur.close()

    def fetch_latest_market_analysis(self, analysis_slot: str) -> StoredMarketAnalysisRecord | None:
        if self._conn is None:
            return None

        sql = (
            f"SELECT id, analysis_date, analysis_slot, scheduled_time_local, model, prompt_version, summary_text, raw_json, updated_at "
            f"FROM {self._analysis_table} "
            "WHERE analysis_slot=%s "
            "ORDER BY updated_at DESC, id DESC "
            "LIMIT 1"
        )
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(sql, (analysis_slot,))
                row = cur.fetchone()
            finally:
                cur.close()

        if not row:
            return None
        return StoredMarketAnalysisRecord(
            row_id=int(row[0]),
            analysis_date=str(row[1] or ""),
            analysis_slot=str(row[2] or ""),
            scheduled_time_local=str(row[3] or ""),
            model=str(row[4] or ""),
            prompt_version=str(row[5] or ""),
            summary_text=str(row[6] or ""),
            raw_json=str(row[7]) if row[7] is not None else None,
            updated_at=str(row[8]) if row[8] is not None else "",
        )

    def fetch_market_analysis(self, analysis_date: str, analysis_slot: str) -> StoredMarketAnalysisRecord | None:
        if self._conn is None:
            return None

        sql = (
            f"SELECT id, analysis_date, analysis_slot, scheduled_time_local, model, prompt_version, summary_text, raw_json, updated_at "
            f"FROM {self._analysis_table} "
            "WHERE analysis_date=%s AND analysis_slot=%s "
            "ORDER BY updated_at DESC, id DESC "
            "LIMIT 1"
        )
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(sql, (analysis_date, analysis_slot))
                row = cur.fetchone()
            finally:
                cur.close()

        if not row:
            return None
        return StoredMarketAnalysisRecord(
            row_id=int(row[0]),
            analysis_date=str(row[1] or ""),
            analysis_slot=str(row[2] or ""),
            scheduled_time_local=str(row[3] or ""),
            model=str(row[4] or ""),
            prompt_version=str(row[5] or ""),
            summary_text=str(row[6] or ""),
            raw_json=str(row[7]) if row[7] is not None else None,
            updated_at=str(row[8]) if row[8] is not None else "",
        )

    def delete_events_older_than_days(self, keep_days: int) -> int:
        if self._conn is None:
            return 0

        safe_days = max(int(keep_days), 1)
        threshold_date = (datetime.now().astimezone().date() - timedelta(days=safe_days)).isoformat()
        sql = (
            f"DELETE FROM {self._event_table} "
            "WHERE DATE(created_at) <= %s"
        )
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(sql, (threshold_date,))
                affected = int(cur.rowcount or 0)
                self._conn.commit()
                return affected
            finally:
                cur.close()

    def delete_retention_older_than_days(self, keep_days: int) -> dict[str, int]:
        if self._conn is None:
            return {"events": 0, "x_posts": 0}

        safe_days = max(int(keep_days), 1)
        threshold_date = (datetime.now().astimezone().date() - timedelta(days=safe_days)).isoformat()
        delete_events_sql = (
            f"DELETE FROM {self._event_table} "
            "WHERE DATE(created_at) <= %s"
        )
        delete_x_posts_sql = (
            f"DELETE FROM {self._x_table} "
            "WHERE DATE(created_at) <= %s"
        )
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(delete_events_sql, (threshold_date,))
                events_deleted = int(cur.rowcount or 0)
                cur.execute(delete_x_posts_sql, (threshold_date,))
                x_posts_deleted = int(cur.rowcount or 0)
                self._conn.commit()
                return {"events": events_deleted, "x_posts": x_posts_deleted}
            finally:
                cur.close()

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
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          UNIQUE KEY uq_event_hash (event_hash),
          KEY idx_push_queue (is_pushed, created_at)
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
        ddl_market = f"""
        CREATE TABLE IF NOT EXISTS `{self._market_table}` (
          id BIGINT NOT NULL AUTO_INCREMENT,
          event_id VARCHAR(128) NOT NULL,
          source VARCHAR(64) NOT NULL,
          trade_date VARCHAR(16) NOT NULL,
          market_session VARCHAR(16) NOT NULL,
          symbol VARCHAR(32) NOT NULL,
          label VARCHAR(64) NOT NULL,
          quote_url VARCHAR(512) NULL,
          open_price DECIMAL(18,4) NULL,
          last_price DECIMAL(18,4) NULL,
          recorded_price DECIMAL(18,4) NULL,
          regular_start_epoch BIGINT NULL,
          regular_end_epoch BIGINT NULL,
          payload_json JSON NULL,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          UNIQUE KEY uq_market_event_symbol (event_id, symbol),
          KEY idx_market_trade_date (trade_date, market_session, symbol, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
        ddl_analysis = f"""
        CREATE TABLE IF NOT EXISTS `{self._analysis_table}` (
          id BIGINT NOT NULL AUTO_INCREMENT,
          analysis_date VARCHAR(16) NOT NULL,
          analysis_slot VARCHAR(32) NOT NULL,
          scheduled_time_local VARCHAR(16) NOT NULL,
          model VARCHAR(64) NOT NULL,
          prompt_version VARCHAR(32) NOT NULL,
          summary_text TEXT NOT NULL,
          events_used INT NOT NULL DEFAULT 0,
          market_rows_used INT NOT NULL DEFAULT 0,
          push_enabled TINYINT(1) NOT NULL DEFAULT 0,
          pushed TINYINT(1) NOT NULL DEFAULT 0,
          raw_json JSON NULL,
          structured_json JSON NULL,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          UNIQUE KEY uq_analysis_slot_date (analysis_date, analysis_slot),
          KEY idx_analysis_created (created_at, analysis_slot)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
        ddl_annotation = f"""
        CREATE TABLE IF NOT EXISTS `{self._annotation_table}` (
          event_row_id BIGINT NOT NULL,
          entities JSON NOT NULL,
          category VARCHAR(32) NOT NULL,
          importance DECIMAL(4,3) NOT NULL,
          sentiment VARCHAR(8) NOT NULL,
          annotator VARCHAR(16) NOT NULL,
          annotator_version VARCHAR(32) NOT NULL,
          annotated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (event_row_id),
          KEY idx_annotation_category (category, importance),
          KEY idx_annotation_annotated_at (annotated_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
        cur = self._conn.cursor()
        try:
            cur.execute(ddl_event)
            cur.execute(ddl_x)
            cur.execute(ddl_market)
            cur.execute(ddl_analysis)
            cur.execute(ddl_annotation)
            self._conn.commit()
            self._migrate_analysis_structured_json(cur)
        finally:
            cur.close()
        # 將 X 貼文資料同步到 t_x_posts，方便後續查詢與分析。
    def _upsert_x_post(self, cur: Any, event: RelayEvent) -> None:
        # 解析 relay event 內的 X raw payload，取出 tweet 主要欄位。
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

    def upsert_market_snapshot(self, payload: dict[str, Any]) -> int:
        if self._conn is None:
            return 0

        snapshot = payload.get("market_snapshot") if isinstance(payload, dict) else None
        if not isinstance(snapshot, dict):
            return 0

        trade_date = str(snapshot.get("trade_date") or "").strip()
        market_session = str(snapshot.get("session") or "").strip().lower()
        indexes = snapshot.get("indexes")
        if not trade_date or market_session not in {"open", "close"} or not isinstance(indexes, list):
            return 0

        event_id = str(payload.get("event_id") or "").strip()
        source = str(payload.get("source") or "us_index_tracker").strip() or "us_index_tracker"
        if not event_id:
            event_id = f"{source}_{market_session}_{trade_date}"

        affected = 0
        with self._lock:
            cur = self._conn.cursor()
            try:
                affected = self._upsert_market_rows(
                    cur=cur,
                    event_id=event_id,
                    source=source,
                    trade_date=trade_date,
                    market_session=market_session,
                    indexes=indexes,
                )
                self._conn.commit()
            finally:
                cur.close()

        return affected

    def _upsert_market_snapshot_from_event(self, cur: Any, event: RelayEvent) -> int:
        snapshot = event.raw.get("market_snapshot") if isinstance(event.raw, dict) else None
        if not isinstance(snapshot, dict):
            return 0

        trade_date = str(snapshot.get("trade_date") or "").strip()
        market_session = str(snapshot.get("session") or "").strip().lower()
        indexes = snapshot.get("indexes")
        if not trade_date or market_session not in {"open", "close"} or not isinstance(indexes, list):
            return 0

        event_id = event.event_id or f"{event.source}_{market_session}_{trade_date}"
        return self._upsert_market_rows(
            cur=cur,
            event_id=event_id,
            source=event.source,
            trade_date=trade_date,
            market_session=market_session,
            indexes=indexes,
        )

    def _upsert_market_rows(
        self,
        cur: Any,
        event_id: str,
        source: str,
        trade_date: str,
        market_session: str,
        indexes: list[Any],
    ) -> int:
        sql = (
            f"INSERT INTO {self._market_table} "
            "(event_id, source, trade_date, market_session, symbol, label, quote_url, open_price, last_price, recorded_price, "
            "regular_start_epoch, regular_end_epoch, payload_json) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE "
            "quote_url=VALUES(quote_url), "
            "open_price=VALUES(open_price), "
            "last_price=VALUES(last_price), "
            "recorded_price=VALUES(recorded_price), "
            "regular_start_epoch=VALUES(regular_start_epoch), "
            "regular_end_epoch=VALUES(regular_end_epoch), "
            "payload_json=VALUES(payload_json)"
        )

        affected = 0
        for entry in indexes:
            if not isinstance(entry, dict):
                continue

            symbol = str(entry.get("symbol") or "").strip()
            label = str(entry.get("label") or symbol).strip() or symbol
            if not symbol:
                continue

            open_price = self._to_decimal_value(entry.get("open_price"))
            last_price = self._to_decimal_value(entry.get("last_price"))
            recorded_price = open_price if market_session == "open" else last_price

            cur.execute(
                sql,
                (
                    event_id,
                    source,
                    trade_date,
                    market_session,
                    symbol,
                    label,
                    str(entry.get("url") or "").strip() or None,
                    open_price,
                    last_price,
                    recorded_price,
                    self._to_int_value(entry.get("regular_start_epoch")),
                    self._to_int_value(entry.get("regular_end_epoch")),
                    json.dumps(entry, ensure_ascii=False),
                ),
            )
            affected += 1
        return affected

    @staticmethod
    def _has_market_snapshot(event: RelayEvent) -> bool:
        if not isinstance(event.raw, dict):
            return False
        return isinstance(event.raw.get("market_snapshot"), dict)

    @staticmethod
    def _event_hash(title: str, url: str) -> str:
        key = f"{' '.join(title.split()).lower()}::{url.strip().lower()}"
        return hashlib.sha1(key.encode("utf-8")).hexdigest()

    @staticmethod
    def _event_hash_for_event(event: RelayEvent) -> str:
        source = (event.source or "").strip().lower()
        if source.startswith("market_context:") and event.event_id:
            return hashlib.sha1(f"{source}::{event.event_id}".encode("utf-8")).hexdigest()
        return MySqlEventStore._event_hash(event.title, event.url)

    @staticmethod
    def _to_decimal_value(value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def _to_int_value(value: Any) -> int | None:
        if isinstance(value, int):
            return value
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None

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
        self._store = None
        self._stop_event = threading.Event()
        self._maintenance_thread = None
        self._daily_cleanup_ran_for_date = None

        if settings.mysql_enabled:
            self._store = MySqlEventStore(settings)
            self._store.initialize()
            logger.info(
                "MySQL ready: %s:%s/%s event_table=%s x_table=%s market_table=%s analysis_table=%s",
                settings.mysql_host,
                settings.mysql_port,
                settings.mysql_database,
                settings.mysql_event_table,
                settings.mysql_x_table,
                settings.mysql_market_table,
                settings.mysql_analysis_table,
            )
        else:
            logger.warning("MySQL storage disabled (RELAY_MYSQL_ENABLED=false)")

        self._start_maintenance_scheduler()

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

    def _start_maintenance_scheduler(self) -> None:
        if self._store is None:
            logger.warning("Maintenance scheduler disabled because MySQL store is unavailable")
            return

        self._maintenance_thread = threading.Thread(target=self._maintenance_loop, daemon=True, name="event-relay-maintenance")
        self._maintenance_thread.start()
        logger.info(
            "Maintenance scheduler started: interval=%ss",
            self._settings.dispatch_interval_seconds,
        )

    def _maintenance_loop(self) -> None:
        interval = max(self._settings.dispatch_interval_seconds, 1)
        while not self._stop_event.is_set():
            try:
                self.maintenance_once()
            except Exception:
                logger.exception("Maintenance loop error")
            self._stop_event.wait(interval)

    def maintenance_once(self) -> None:
        if self._store is None:
            return

        self._run_daily_retention_cleanup_if_due()
        logger.info("Maintenance tick complete; Python service does not perform LINE delivery")

    def _run_daily_retention_cleanup_if_due(self) -> None:
        if self._store is None:
            return
        if not self._settings.retention_enabled:
            return

        now_local = datetime.now().astimezone()
        if now_local.hour == 0 and now_local.minute < 3:
            return

        today_local = now_local.date()
        if self._daily_cleanup_ran_for_date == today_local:
            return

        result = self._store.delete_retention_older_than_days(keep_days=self._settings.retention_keep_days)
        self._daily_cleanup_ran_for_date = today_local
        logger.info(
            "Daily retention cleanup executed at %s: keep_days=%d events_deleted=%d x_posts_deleted=%d",
            now_local.isoformat(),
            self._settings.retention_keep_days,
            int(result.get("events", 0)),
            int(result.get("x_posts", 0)),
        )

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
    def _normalize_summary(value: str) -> str:
        text = html.unescape(value)
        text = re.sub(r"<[^>]+>", " ", text)
        text = " ".join(text.split())
        return text[:1200]

    @staticmethod
    def _is_test_source(source: str | None) -> bool:
        value = (source or "").strip().lower()
        return value == "local_live_test" or value.startswith("manual_test")

    @staticmethod
    def _is_older_than_days(published_at: str | None, days: int, now_local: datetime | None = None) -> bool:
        if not published_at:
            return False
        parsed = RelayProcessor._parse_published_at(published_at)
        if parsed is None:
            return False
        ref_now = now_local or datetime.now().astimezone()
        return parsed.date() <= (ref_now.date() - timedelta(days=max(int(days), 0) + 1))

    @staticmethod
    def _allow_event_date(published_at: str | None) -> bool:
        # Keep events within recent 2 days + today (local timezone).
        if not published_at:
            return False
        parsed = RelayProcessor._parse_published_at(published_at)
        if parsed is None:
            return False
        now_local = datetime.now().astimezone().date()
        earliest_allowed = now_local - timedelta(days=2)
        return parsed.date() >= earliest_allowed

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
