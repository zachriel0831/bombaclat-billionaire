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
    """封裝 Relay Event 相關資料與行為。"""
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
    """封裝 Summary Event 相關資料與行為。"""
    row_id: int
    source: str
    title: str
    url: str
    summary: str
    published_at: str | None
    created_at: str
    raw_json: str | None = None
    event_id: str | None = None


@dataclass
class MarketSnapshotRow:
    """封裝 Market Snapshot Row 相關資料與行為。"""
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
class MarketQuoteSnapshot:
    """封裝 Market Quote Snapshot 相關資料與行為。"""
    symbol: str
    market: str
    session: str
    ts: str
    open_price: float | None
    high_price: float | None
    low_price: float | None
    close_price: float | None
    prev_close: float | None
    volume: int | None
    turnover: float | None
    change_pct: float | None
    source: str
    raw_json: str | None = None


@dataclass
class MarketAnalysisRecord:
    """封裝 Market Analysis Record 相關資料與行為。"""
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
    """封裝 Stored Market Analysis Record 相關資料與行為。"""
    row_id: int
    analysis_date: str
    analysis_slot: str
    scheduled_time_local: str
    model: str
    prompt_version: str
    summary_text: str
    raw_json: str | None
    updated_at: str


@dataclass
class StoredEventEmbedding:
    """封裝 Stored Event Embedding 相關資料與行為。"""
    event_row_id: int
    event_id: str | None
    source: str
    title: str
    url: str
    summary: str
    published_at: str | None
    created_at: str
    embedding_model: str
    embedding_dim: int
    embedding: list[float]
    text_hash: str


@dataclass
class AnalysisEmbeddingSource:
    """封裝 Analysis Embedding Source 相關資料與行為。"""
    row_id: int
    analysis_date: str
    analysis_slot: str
    summary_text: str
    raw_json: str | None
    updated_at: str


class MySqlEventStore:
    """封裝 My Sql Event Store 相關資料與行為。"""
    def __init__(self, settings: RelaySettings) -> None:
        """初始化物件狀態與必要依賴。"""
        self._settings = settings
        self._event_table = settings.mysql_event_table
        self._x_table = settings.mysql_x_table
        self._market_table = settings.mysql_market_table
        self._quote_snapshot_table = settings.mysql_quote_snapshot_table
        self._analysis_table = settings.mysql_analysis_table
        self._annotation_table = settings.mysql_annotation_table
        self._event_embedding_table = settings.mysql_event_embedding_table
        self._analysis_embedding_table = settings.mysql_analysis_embedding_table
        self._connector = self._import_mysql_connector()
        self._conn = None
        self._lock = threading.RLock()

    def initialize(self) -> None:
        """執行 initialize 方法的主要邏輯。"""
        self._create_database_if_needed()
        self._connect_database()
        self._create_tables_if_needed()

    def enqueue_event_if_new(self, event: RelayEvent) -> bool:
        """執行 enqueue event if new 方法的主要邏輯。"""
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")

        # 事件表是整條資料鏈的主表；若來源是 X 或帶市場快照，會在同一個 transaction
        # 內順手同步到附屬表，避免主表/副表只寫成功一半。
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
        """抓取 fetch recent summary events 對應的資料或結果。"""
        if self._conn is None:
            return []

        safe_days = max(int(days), 1)
        safe_limit = max(int(limit), 1)
        # Use the auto-increment primary key as the recency order. Recent
        # market-context rows can carry large official payloads, and filesort
        # over created_at/raw_json can exceed MySQL's sort buffer on small DBs.
        sql = (
            f"SELECT id, event_id, source, title, url, summary, published_at, created_at, raw_json "
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
                    event_id=str(row[1]) if row[1] is not None else None,
                    source=str(row[2]),
                    title=str(row[3]),
                    url=str(row[4]),
                    summary=str(row[5] or ""),
                    published_at=str(row[6]) if row[6] is not None else None,
                    created_at=str(row[7]),
                    raw_json=str(row[8]) if row[8] is not None else None,
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
        """新增或更新 upsert event annotation 對應的資料或結果。"""
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

    def fetch_events_missing_embeddings(
        self,
        *,
        days: int,
        limit: int,
        embedding_model: str,
    ) -> list[SummaryEvent]:
        """抓取 fetch events missing embeddings 對應的資料或結果。"""
        if self._conn is None:
            return []

        safe_days = max(int(days), 1)
        safe_limit = max(int(limit), 1)
        sql = (
            f"SELECT e.id, e.event_id, e.source, e.title, e.url, e.summary, "
            f"e.published_at, e.created_at, e.raw_json "
            f"FROM {self._event_table} e "
            f"LEFT JOIN {self._event_embedding_table} emb "
            "ON emb.event_row_id = e.id AND emb.embedding_model = %s "
            "WHERE e.created_at >= (NOW() - INTERVAL %s DAY) "
            "AND e.source NOT REGEXP '^(local_live_test|manual_test)' "
            "AND emb.event_row_id IS NULL "
            "ORDER BY e.id DESC "
            "LIMIT %s"
        )
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(sql, (embedding_model, safe_days, safe_limit))
                rows = cur.fetchall()
            finally:
                cur.close()

        return [
            SummaryEvent(
                row_id=int(row[0]),
                event_id=str(row[1]) if row[1] is not None else None,
                source=str(row[2] or ""),
                title=str(row[3] or ""),
                url=str(row[4] or ""),
                summary=str(row[5] or ""),
                published_at=str(row[6]) if row[6] is not None else None,
                created_at=str(row[7]) if row[7] is not None else "",
                raw_json=str(row[8]) if row[8] is not None else None,
            )
            for row in rows
        ]

    def upsert_event_embedding(
        self,
        *,
        event: SummaryEvent,
        embedding_model: str,
        embedding: list[float],
        text_hash: str,
    ) -> None:
        """新增或更新 upsert event embedding 對應的資料或結果。"""
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")

        embedding_json = json.dumps(list(embedding), ensure_ascii=False)
        sql = (
            f"INSERT INTO {self._event_embedding_table} "
            "(event_row_id, event_id, source, title, url, summary, published_at, "
            "embedding_model, embedding_dim, embedding_json, text_hash) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE "
            "event_id=VALUES(event_id), "
            "source=VALUES(source), "
            "title=VALUES(title), "
            "url=VALUES(url), "
            "summary=VALUES(summary), "
            "published_at=VALUES(published_at), "
            "embedding_dim=VALUES(embedding_dim), "
            "embedding_json=VALUES(embedding_json), "
            "text_hash=VALUES(text_hash), "
            "indexed_at=CURRENT_TIMESTAMP"
        )
        values = (
            int(event.row_id),
            event.event_id,
            event.source,
            event.title,
            event.url,
            event.summary,
            event.published_at,
            embedding_model,
            len(embedding),
            embedding_json,
            text_hash,
        )
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(sql, values)
                self._conn.commit()
            finally:
                cur.close()

    def fetch_event_embedding_candidates(
        self,
        *,
        embedding_model: str,
        limit: int,
    ) -> list[StoredEventEmbedding]:
        """抓取 fetch event embedding candidates 對應的資料或結果。"""
        if self._conn is None:
            return []

        safe_limit = max(int(limit), 1)
        sql = (
            f"SELECT event_row_id, event_id, source, title, url, summary, published_at, "
            "created_at, embedding_model, embedding_dim, embedding_json, text_hash "
            f"FROM {self._event_embedding_table} "
            "WHERE embedding_model = %s "
            "ORDER BY event_row_id DESC "
            "LIMIT %s"
        )
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(sql, (embedding_model, safe_limit))
                rows = cur.fetchall()
            finally:
                cur.close()

        candidates: list[StoredEventEmbedding] = []
        for row in rows:
            try:
                embedding = json.loads(row[10]) if isinstance(row[10], str) else row[10]
            except (TypeError, ValueError):
                embedding = []
            if not isinstance(embedding, list):
                embedding = []
            candidates.append(
                StoredEventEmbedding(
                    event_row_id=int(row[0]),
                    event_id=str(row[1]) if row[1] is not None else None,
                    source=str(row[2] or ""),
                    title=str(row[3] or ""),
                    url=str(row[4] or ""),
                    summary=str(row[5] or ""),
                    published_at=str(row[6]) if row[6] is not None else None,
                    created_at=str(row[7]) if row[7] is not None else "",
                    embedding_model=str(row[8] or ""),
                    embedding_dim=int(row[9] or 0),
                    embedding=[float(value) for value in embedding if isinstance(value, (int, float))],
                    text_hash=str(row[11] or ""),
                )
            )
        return candidates

    def fetch_analyses_missing_embeddings(
        self,
        *,
        limit: int,
        embedding_model: str,
    ) -> list[AnalysisEmbeddingSource]:
        """抓取 fetch analyses missing embeddings 對應的資料或結果。"""
        if self._conn is None:
            return []

        safe_limit = max(int(limit), 1)
        sql = (
            f"SELECT a.id, a.analysis_date, a.analysis_slot, a.summary_text, a.raw_json, a.updated_at "
            f"FROM {self._analysis_table} a "
            f"LEFT JOIN {self._analysis_embedding_table} emb "
            "ON emb.analysis_id = a.id AND emb.embedding_model = %s "
            "WHERE emb.analysis_id IS NULL "
            "ORDER BY a.id DESC "
            "LIMIT %s"
        )
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(sql, (embedding_model, safe_limit))
                rows = cur.fetchall()
            finally:
                cur.close()

        return [
            AnalysisEmbeddingSource(
                row_id=int(row[0]),
                analysis_date=str(row[1] or ""),
                analysis_slot=str(row[2] or ""),
                summary_text=str(row[3] or ""),
                raw_json=str(row[4]) if row[4] is not None else None,
                updated_at=str(row[5]) if row[5] is not None else "",
            )
            for row in rows
        ]

    def upsert_analysis_embedding(
        self,
        *,
        analysis: AnalysisEmbeddingSource,
        embedding_model: str,
        embedding: list[float],
        text_hash: str,
        outcome_json: dict[str, Any] | None = None,
    ) -> None:
        """新增或更新 upsert analysis embedding 對應的資料或結果。"""
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")

        sql = (
            f"INSERT INTO {self._analysis_embedding_table} "
            "(analysis_id, analysis_date, analysis_slot, embedding_model, embedding_dim, "
            "embedding_json, text_hash, outcome_json) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE "
            "analysis_date=VALUES(analysis_date), "
            "analysis_slot=VALUES(analysis_slot), "
            "embedding_dim=VALUES(embedding_dim), "
            "embedding_json=VALUES(embedding_json), "
            "text_hash=VALUES(text_hash), "
            "outcome_json=VALUES(outcome_json), "
            "indexed_at=CURRENT_TIMESTAMP"
        )
        values = (
            int(analysis.row_id),
            analysis.analysis_date,
            analysis.analysis_slot,
            embedding_model,
            len(embedding),
            json.dumps(list(embedding), ensure_ascii=False),
            text_hash,
            json.dumps(outcome_json or {"status": "unlabeled"}, ensure_ascii=False),
        )
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(sql, values)
                self._conn.commit()
            finally:
                cur.close()

    def fetch_recent_market_snapshots(self, hours: int, limit: int) -> list[MarketSnapshotRow]:
        """抓取 fetch recent market snapshots 對應的資料或結果。"""
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
        """新增或更新 upsert market analysis 對應的資料或結果。"""
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")

        # 分析結果以 (analysis_date, analysis_slot) 為唯一鍵覆寫，讓排程重跑時會更新同一筆，
        # 而不是每天堆出多份同 slot 報告。
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

    def upsert_market_quote_snapshot(self, snapshot: MarketQuoteSnapshot) -> None:
        """新增或更新 upsert market quote snapshot 對應的資料或結果。"""
        if self._conn is None:
            raise RuntimeError("MySQL not initialized")

        sql = (
            f"INSERT INTO {self._quote_snapshot_table} "
            "(symbol, market, session, ts, open_price, high_price, low_price, close_price, "
            "prev_close, volume, turnover, change_pct, source, raw_json) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE "
            "open_price=VALUES(open_price), "
            "high_price=VALUES(high_price), "
            "low_price=VALUES(low_price), "
            "close_price=VALUES(close_price), "
            "prev_close=VALUES(prev_close), "
            "volume=VALUES(volume), "
            "turnover=VALUES(turnover), "
            "change_pct=VALUES(change_pct), "
            "raw_json=VALUES(raw_json)"
        )
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(
                    sql,
                    (
                        snapshot.symbol,
                        snapshot.market,
                        snapshot.session,
                        snapshot.ts,
                        snapshot.open_price,
                        snapshot.high_price,
                        snapshot.low_price,
                        snapshot.close_price,
                        snapshot.prev_close,
                        snapshot.volume,
                        snapshot.turnover,
                        snapshot.change_pct,
                        snapshot.source,
                        snapshot.raw_json,
                    ),
                )
                self._conn.commit()
            finally:
                cur.close()

    def fetch_latest_market_analysis(self, analysis_slot: str) -> StoredMarketAnalysisRecord | None:
        """抓取 fetch latest market analysis 對應的資料或結果。"""
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
        """抓取 fetch market analysis 對應的資料或結果。"""
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
        """刪除 delete events older than days 對應的資料或結果。"""
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
        """刪除 delete retention older than days 對應的資料或結果。"""
        if self._conn is None:
            return {"events": 0, "x_posts": 0}

        safe_days = max(int(keep_days), 1)
        threshold_date = (datetime.now().astimezone().date() - timedelta(days=safe_days)).isoformat()
        # t_relay_events 與 t_x_posts 必須一起清，否則事件被刪掉但原始貼文還留著，
        # 後續查 gap 或做分析時會出現時間窗不一致。
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
        """執行 create database if needed 方法的主要邏輯。"""
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
        """執行 connect database 方法的主要邏輯。"""
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
        """執行 create tables if needed 方法的主要邏輯。"""
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
        ddl_quote_snapshot = f"""
        CREATE TABLE IF NOT EXISTS `{self._quote_snapshot_table}` (
          id BIGINT NOT NULL AUTO_INCREMENT,
          symbol VARCHAR(32) NOT NULL,
          market VARCHAR(16) NOT NULL,
          session VARCHAR(16) NOT NULL,
          ts DATETIME NOT NULL,
          open_price DECIMAL(18,4) NULL,
          high_price DECIMAL(18,4) NULL,
          low_price DECIMAL(18,4) NULL,
          close_price DECIMAL(18,4) NULL,
          prev_close DECIMAL(18,4) NULL,
          volume BIGINT NULL,
          turnover DECIMAL(20,2) NULL,
          change_pct DECIMAL(10,4) NULL,
          source VARCHAR(64) NOT NULL,
          raw_json JSON NULL,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          UNIQUE KEY uq_quote_symbol_ts_source (symbol, ts, source),
          KEY idx_quote_market_ts (market, ts),
          KEY idx_quote_symbol_ts (symbol, ts)
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
        ddl_event_embeddings = f"""
        CREATE TABLE IF NOT EXISTS `{self._event_embedding_table}` (
          event_row_id BIGINT NOT NULL,
          event_id VARCHAR(128) NULL,
          source VARCHAR(64) NOT NULL,
          title TEXT NOT NULL,
          url TEXT NOT NULL,
          summary TEXT NULL,
          published_at VARCHAR(64) NULL,
          embedding_model VARCHAR(64) NOT NULL,
          embedding_dim INT NOT NULL,
          embedding_json JSON NOT NULL,
          text_hash CHAR(40) NOT NULL,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          indexed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (event_row_id, embedding_model),
          KEY idx_event_embedding_model (embedding_model, indexed_at),
          KEY idx_event_embedding_source (source, indexed_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
        ddl_analysis_embeddings = f"""
        CREATE TABLE IF NOT EXISTS `{self._analysis_embedding_table}` (
          analysis_id BIGINT NOT NULL,
          analysis_date VARCHAR(16) NOT NULL,
          analysis_slot VARCHAR(32) NOT NULL,
          embedding_model VARCHAR(64) NOT NULL,
          embedding_dim INT NOT NULL,
          embedding_json JSON NOT NULL,
          text_hash CHAR(40) NOT NULL,
          outcome_json JSON NULL,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          indexed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (analysis_id, embedding_model),
          KEY idx_analysis_embedding_slot (analysis_slot, analysis_date),
          KEY idx_analysis_embedding_model (embedding_model, indexed_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
        cur = self._conn.cursor()
        try:
            cur.execute(ddl_event)
            cur.execute(ddl_x)
            cur.execute(ddl_market)
            cur.execute(ddl_quote_snapshot)
            cur.execute(ddl_analysis)
            cur.execute(ddl_annotation)
            cur.execute(ddl_event_embeddings)
            cur.execute(ddl_analysis_embeddings)
            self._conn.commit()
            self._migrate_analysis_structured_json(cur)
        finally:
            cur.close()
        # 將 X 貼文資料同步到 t_x_posts，方便後續查詢與分析。
    def _upsert_x_post(self, cur: Any, event: RelayEvent) -> None:
        # 解析 relay event 內的 X raw payload，取出 tweet 主要欄位。
        """新增或更新 upsert x post 對應的資料或結果。"""
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
        """新增或更新 upsert market snapshot 對應的資料或結果。"""
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
        """新增或更新 upsert market snapshot from event 對應的資料或結果。"""
        snapshot = event.raw.get("market_snapshot") if isinstance(event.raw, dict) else None
        if not isinstance(snapshot, dict):
            return 0

        # 市場快照不是獨立 API 寫入，而是夾在 relay event.raw 裡一起進來；
        # 這裡把事件層的 payload 再拆成 index-level rows，方便分析直接查結構化行情。
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
        """新增或更新 upsert market rows 對應的資料或結果。"""
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

            # open session 記錄當時開盤價，close session 記錄收盤/最新價；
            # recorded_price 會依 session 選擇對應欄位，讓下游少做判斷。
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
        """判斷是否具備 has market snapshot 對應的資料或結果。"""
        if not isinstance(event.raw, dict):
            return False
        return isinstance(event.raw.get("market_snapshot"), dict)

    @staticmethod
    def _event_hash(title: str, url: str) -> str:
        """執行 event hash 方法的主要邏輯。"""
        key = f"{' '.join(title.split()).lower()}::{url.strip().lower()}"
        return hashlib.sha1(key.encode("utf-8")).hexdigest()

    @staticmethod
    def _event_hash_for_event(event: RelayEvent) -> str:
        """執行 event hash for event 方法的主要邏輯。"""
        source = (event.source or "").strip().lower()
        # market_context 類事件常常 url/title 長得很像；若仍只靠 title+url 去重，
        # 同一天不同資料點可能互相吃掉，所以改用 event_id 做穩定去重。
        if source.startswith("market_context:") and event.event_id:
            return hashlib.sha1(f"{source}::{event.event_id}".encode("utf-8")).hexdigest()
        return MySqlEventStore._event_hash(event.title, event.url)

    @staticmethod
    def _to_decimal_value(value: Any) -> float | None:
        """轉換 to decimal value 對應的資料或結果。"""
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
        """轉換 to int value 對應的資料或結果。"""
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
        """執行 import mysql connector 方法的主要邏輯。"""
        try:
            import mysql.connector  # type: ignore
        except Exception as exc:
            raise RuntimeError("mysql-connector-python is required. Run: pip install -e .") from exc
        return mysql.connector


class RelayProcessor:
    """封裝 Relay Processor 相關資料與行為。"""
    def __init__(self, settings: RelaySettings) -> None:
        """初始化物件狀態與必要依賴。"""
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
        # /events 相容入口允許單筆、批次、或 {events:[...]} 三種格式；
        # 這裡統一轉成 RelayEvent 後再做寫庫，讓上游 crawler 不必知道底層細節。
        """執行 process payload 方法的主要邏輯。"""
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

    def process_quote_snapshots(self, payload: Any) -> dict[str, Any]:
        """Persist a batch of MarketQuoteSnapshot rows. Payload is a list of dicts."""
        if not isinstance(payload, list):
            raise ValueError("payload must be a JSON array of snapshot rows")

        stored = 0
        skipped = 0
        failed = 0
        results: list[dict[str, Any]] = []

        for idx, row in enumerate(payload):
            if not isinstance(row, dict):
                skipped += 1
                results.append({"index": idx, "status": "skipped", "reason": "not_object"})
                continue
            try:
                snapshot = self._coerce_quote_snapshot(row)
            except ValueError as exc:
                skipped += 1
                results.append({"index": idx, "status": "skipped", "reason": str(exc)})
                continue

            if self._store is None:
                # Dry-run path; useful in tests + when MySQL is disabled.
                results.append({"index": idx, "status": "dropped", "reason": "mysql_disabled"})
                continue

            try:
                self._store.upsert_market_quote_snapshot(snapshot)
                stored += 1
                results.append({"index": idx, "status": "stored", "symbol": snapshot.symbol})
            except Exception as exc:  # noqa: BLE001
                failed += 1
                logger.exception("Failed to upsert quote snapshot symbol=%s", snapshot.symbol)
                results.append({"index": idx, "status": "failed", "error": str(exc)})

        return {
            "received": len(payload),
            "stored": stored,
            "skipped": skipped,
            "failed": failed,
            "results": results,
        }

    @staticmethod
    def _coerce_quote_snapshot(row: dict[str, Any]) -> "MarketQuoteSnapshot":
        """轉換並校正 coerce quote snapshot 對應的資料或結果。"""
        symbol = str(row.get("symbol") or "").strip()
        market = str(row.get("market") or "").strip()
        session = str(row.get("session") or "regular").strip()
        ts = str(row.get("ts") or "").strip()
        if not symbol or not market or not ts:
            raise ValueError("symbol, market, ts are required")

        def _opt_float(v: Any) -> float | None:
            """執行 opt float 方法的主要邏輯。"""
            if v is None:
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        def _opt_int(v: Any) -> int | None:
            """執行 opt int 方法的主要邏輯。"""
            if v is None:
                return None
            try:
                return int(v)
            except (TypeError, ValueError):
                return None

        raw = row.get("raw_json")
        raw_json_str: str | None = None
        if raw is not None:
            raw_json_str = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)

        return MarketQuoteSnapshot(
            symbol=symbol,
            market=market,
            session=session,
            ts=ts,
            open_price=_opt_float(row.get("open_price") or row.get("open")),
            high_price=_opt_float(row.get("high_price") or row.get("high")),
            low_price=_opt_float(row.get("low_price") or row.get("low")),
            close_price=_opt_float(row.get("close_price") or row.get("close") or row.get("price")),
            prev_close=_opt_float(row.get("prev_close")),
            volume=_opt_int(row.get("volume")),
            turnover=_opt_float(row.get("turnover")),
            change_pct=_opt_float(row.get("change_pct")),
            source=str(row.get("source") or "yfinance").strip(),
            raw_json=raw_json_str,
        )

    def _start_maintenance_scheduler(self) -> None:
        """執行 start maintenance scheduler 方法的主要邏輯。"""
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
        """執行 maintenance loop 方法的主要邏輯。"""
        interval = max(self._settings.dispatch_interval_seconds, 1)
        while not self._stop_event.is_set():
            try:
                self.maintenance_once()
            except Exception:
                logger.exception("Maintenance loop error")
            self._stop_event.wait(interval)

    def maintenance_once(self) -> None:
        """執行 maintenance once 方法的主要邏輯。"""
        if self._store is None:
            return

        self._run_daily_retention_cleanup_if_due()
        logger.info("Maintenance tick complete; Python service does not perform LINE delivery")

    def _run_daily_retention_cleanup_if_due(self) -> None:
        """執行 run daily retention cleanup if due 方法的主要邏輯。"""
        if self._store is None:
            return
        if not self._settings.retention_enabled:
            return

        now_local = datetime.now().astimezone()
        # 避開 00:00 剛過的幾分鐘，減少和外部固定排程、跨日寫入同時搶表的機率。
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
        """取出 extract events 對應的資料或結果。"""
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
            # 入口層先做基本時效過濾，避免過舊事件進到去重與寫庫流程後才被發現。
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
        """正規化 normalize summary 對應的資料或結果。"""
        text = html.unescape(value)
        text = re.sub(r"<[^>]+>", " ", text)
        text = " ".join(text.split())
        return text[:1200]

    @staticmethod
    def _is_test_source(source: str | None) -> bool:
        """判斷 is test source 對應的資料或結果。"""
        value = (source or "").strip().lower()
        return value == "local_live_test" or value.startswith("manual_test")

    @staticmethod
    def _is_older_than_days(published_at: str | None, days: int, now_local: datetime | None = None) -> bool:
        """判斷 is older than days 對應的資料或結果。"""
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
        """執行 allow event date 方法的主要邏輯。"""
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
        """解析 parse published at 對應的資料或結果。"""
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
