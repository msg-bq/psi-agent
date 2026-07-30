"""SQLite persistence for Event Daemon raw input, inbox, and leases."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from collections.abc import Callable
from functools import partial
from typing import Any

import anyio
from anyio import to_thread

from psi_agent.eventd.schema import CloudEvent, EventConflictError, Subscription

_SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_delivery (
    receipt_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    connection_id TEXT NOT NULL,
    transport TEXT NOT NULL,
    provider_event_id TEXT NOT NULL,
    raw_payload TEXT NOT NULL,
    received_at INTEGER NOT NULL,
    normalize_state TEXT NOT NULL,
    normalize_started_at INTEGER NOT NULL DEFAULT 0,
    normalize_attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS raw_delivery_retry_idx
    ON raw_delivery(normalize_state, received_at);
CREATE TABLE IF NOT EXISTS inbox_event (
    event_seq INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    event_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    envelope_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    received_at INTEGER NOT NULL,
    conflict_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE(source, event_id)
);
CREATE TABLE IF NOT EXISTS subscription (
    subscription_id TEXT PRIMARY KEY,
    filter_json TEXT NOT NULL,
    lease_seconds INTEGER NOT NULL,
    max_attempts INTEGER NOT NULL,
    dead_letter_after_seconds INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS delivery (
    delivery_id TEXT PRIMARY KEY,
    subscription_id TEXT NOT NULL REFERENCES subscription(subscription_id),
    event_seq INTEGER NOT NULL REFERENCES inbox_event(event_seq),
    state TEXT NOT NULL,
    available_at INTEGER NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    lease_owner TEXT NOT NULL DEFAULT '',
    lease_token TEXT NOT NULL DEFAULT '',
    lease_until INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    acked_at INTEGER,
    created_at INTEGER NOT NULL,
    UNIQUE(subscription_id, event_seq)
);
CREATE INDEX IF NOT EXISTS delivery_claim_idx
    ON delivery(subscription_id, state, available_at, event_seq);
CREATE TABLE IF NOT EXISTS connection_state (
    connection_id TEXT NOT NULL,
    state_key TEXT NOT NULL,
    state_value TEXT NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY(connection_id, state_key)
);
"""


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


class EventStore:
    """AnyIO facade over short-lived SQLite transactions."""

    def __init__(self, path: str) -> None:
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode = WAL")
        db.execute("PRAGMA synchronous = FULL")
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA busy_timeout = 5000")
        return db

    async def _run(self, func: Callable[..., Any], *args: object) -> Any:
        return await to_thread.run_sync(partial(func, *args))

    async def initialize(self) -> None:
        path = anyio.Path(self.path)
        await path.parent.mkdir(parents=True, exist_ok=True)
        await self._run(self._initialize_sync)

    def _initialize_sync(self) -> None:
        with self._connect() as db:
            db.executescript(_SCHEMA)
            columns = {str(row["name"]) for row in db.execute("PRAGMA table_info(raw_delivery)")}
            if "normalize_started_at" not in columns:
                db.execute("ALTER TABLE raw_delivery ADD COLUMN normalize_started_at INTEGER NOT NULL DEFAULT 0")

    async def ready(self) -> bool:
        try:
            return bool(await self._run(self._ready_sync))
        except sqlite3.Error:
            return False

    def _ready_sync(self) -> bool:
        with self._connect() as db:
            tables = {
                str(row["name"])
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
                    "('raw_delivery', 'inbox_event', 'subscription', 'delivery', 'connection_state')"
                )
            }
            if tables != {"raw_delivery", "inbox_event", "subscription", "delivery", "connection_state"}:
                return False
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO connection_state(connection_id, state_key, state_value, updated_at) "
                "VALUES ('__eventd_ready__', 'probe', 'ok', ?) "
                "ON CONFLICT(connection_id, state_key) DO UPDATE SET updated_at=excluded.updated_at",
                (_now_ms(),),
            )
            db.rollback()
        return True

    async def upsert_subscription(self, subscription: Subscription) -> None:
        await self._run(self._upsert_subscription_sync, subscription)

    def _upsert_subscription_sync(self, subscription: Subscription) -> None:
        with self._connect() as db:
            db.execute(
                """INSERT INTO subscription(
                       subscription_id, filter_json, lease_seconds, max_attempts,
                       dead_letter_after_seconds, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(subscription_id) DO UPDATE SET
                       filter_json=excluded.filter_json,
                       lease_seconds=excluded.lease_seconds,
                       max_attempts=excluded.max_attempts,
                       dead_letter_after_seconds=excluded.dead_letter_after_seconds,
                       updated_at=excluded.updated_at""",
                (
                    subscription.id,
                    json.dumps(subscription.filter_dict(), ensure_ascii=False, sort_keys=True),
                    subscription.lease_seconds,
                    subscription.max_attempts,
                    subscription.dead_letter_after_seconds,
                    _now_ms(),
                ),
            )

    async def receive_raw(
        self,
        *,
        provider: str,
        connection_id: str,
        transport: str,
        provider_event_id: str,
        raw_payload: object,
    ) -> str:
        receipt_id = f"receipt_{uuid.uuid4().hex}"
        payload = json.dumps(raw_payload, ensure_ascii=False, sort_keys=True, allow_nan=False)
        await self._run(
            self._receive_raw_sync,
            receipt_id,
            provider,
            connection_id,
            transport,
            provider_event_id,
            payload,
        )
        return receipt_id

    def _receive_raw_sync(
        self,
        receipt_id: str,
        provider: str,
        connection_id: str,
        transport: str,
        provider_event_id: str,
        payload: str,
    ) -> None:
        with self._connect() as db:
            db.execute(
                """INSERT INTO raw_delivery(
                       receipt_id, provider, connection_id, transport, provider_event_id,
                       raw_payload, received_at, normalize_state
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, 'RECEIVED')""",
                (receipt_id, provider, connection_id, transport, provider_event_id, payload, _now_ms()),
            )

    async def set_raw_state(self, receipt_id: str, state: str, error: str = "") -> None:
        await self._run(self._set_raw_state_sync, receipt_id, state, error)

    def _set_raw_state_sync(self, receipt_id: str, state: str, error: str) -> None:
        now = _now_ms()
        with self._connect() as db:
            db.execute(
                """UPDATE raw_delivery
                   SET normalize_state=?,
                       normalize_attempts=normalize_attempts + CASE WHEN ?='NORMALIZING' THEN 1 ELSE 0 END,
                       normalize_started_at=CASE WHEN ?='NORMALIZING' THEN ? ELSE 0 END,
                       last_error=?
                   WHERE receipt_id=?""",
                (state, state, state, now, error[:4000], receipt_id),
            )

    async def pending_raw(
        self, connection_id: str, limit: int = 20, stale_after_seconds: int = 300
    ) -> list[dict[str, Any]]:
        return await self._run(self._pending_raw_sync, connection_id, limit, stale_after_seconds)

    def _pending_raw_sync(self, connection_id: str, limit: int, stale_after_seconds: int) -> list[dict[str, Any]]:
        stale_before = _now_ms() - max(0, stale_after_seconds) * 1000
        with self._connect() as db:
            rows = db.execute(
                """SELECT receipt_id, provider_event_id, raw_payload, normalize_attempts
                   FROM raw_delivery
                   WHERE connection_id=? AND (
                       normalize_state IN ('RECEIVED', 'NORMALIZE_RETRY') OR
                       (normalize_state='NORMALIZING' AND normalize_started_at<=?)
                   )
                   ORDER BY received_at LIMIT ?""",
                (connection_id, stale_before, limit),
            ).fetchall()
        return [
            {
                "receipt_id": row["receipt_id"],
                "provider_event_id": row["provider_event_id"],
                "raw_payload": json.loads(row["raw_payload"]),
                "normalize_attempts": row["normalize_attempts"],
            }
            for row in rows
        ]

    async def ingest(self, event: CloudEvent, subscription_ids: list[str]) -> tuple[str, int]:
        return await self._run(self._ingest_sync, event, subscription_ids)

    async def contains_event(self, source: str, event_id: str) -> bool:
        return bool(await self._run(self._contains_event_sync, source, event_id))

    def _contains_event_sync(self, source: str, event_id: str) -> bool:
        with self._connect() as db:
            row = db.execute("SELECT 1 FROM inbox_event WHERE source=? AND event_id=?", (source, event_id)).fetchone()
        return row is not None

    def _ingest_sync(self, event: CloudEvent, subscription_ids: list[str]) -> tuple[str, int]:
        envelope = event.canonical_json()
        content_hash = event.content_hash()
        now = _now_ms()
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT event_seq, content_hash FROM inbox_event WHERE source=? AND event_id=?",
                (event.source, event.id),
            ).fetchone()
            if existing is not None:
                event_seq = int(existing["event_seq"])
                if existing["content_hash"] != content_hash:
                    db.execute("UPDATE inbox_event SET conflict_count=conflict_count+1 WHERE event_seq=?", (event_seq,))
                    db.commit()
                    raise EventConflictError(f"conflicting content for ({event.source!r}, {event.id!r})")
                status = "duplicate"
            else:
                cursor = db.execute(
                    """INSERT INTO inbox_event(
                           source, event_id, event_type, envelope_json, content_hash, received_at
                       ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (event.source, event.id, event.type, envelope, content_hash, now),
                )
                if cursor.lastrowid is None:
                    raise RuntimeError("SQLite did not return an event sequence")
                event_seq = cursor.lastrowid
                status = "created"
            for subscription_id in subscription_ids:
                db.execute(
                    """INSERT OR IGNORE INTO delivery(
                           delivery_id, subscription_id, event_seq, state, available_at, created_at
                       ) VALUES (?, ?, ?, 'READY', ?, ?)""",
                    (f"delivery_{uuid.uuid4().hex}", subscription_id, event_seq, now, now),
                )
            db.commit()
            return status, event_seq
        except Exception:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

    async def claim(
        self,
        *,
        subscription_id: str,
        instance_id: str,
        limit: int,
        lease_seconds: int,
    ) -> list[dict[str, Any]]:
        return await self._run(self._claim_sync, subscription_id, instance_id, limit, lease_seconds)

    def _claim_sync(
        self,
        subscription_id: str,
        instance_id: str,
        limit: int,
        lease_seconds: int,
    ) -> list[dict[str, Any]]:
        now = _now_ms()
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                """UPDATE delivery SET state='READY', lease_owner='', lease_token='', lease_until=0
                   WHERE subscription_id=? AND state='LEASED' AND lease_until<=?""",
                (subscription_id, now),
            )
            db.execute(
                """UPDATE delivery SET state='DEAD', last_error='maximum attempts exhausted'
                   WHERE subscription_id=? AND state='READY' AND attempt_count >= (
                       SELECT max_attempts FROM subscription s WHERE s.subscription_id=delivery.subscription_id
                   )""",
                (subscription_id,),
            )
            db.execute(
                """UPDATE delivery SET state='DEAD', last_error='delivery retention expired'
                   WHERE subscription_id=? AND state='READY' AND created_at + 1000 * (
                       SELECT dead_letter_after_seconds FROM subscription s
                       WHERE s.subscription_id=delivery.subscription_id
                   ) <= ?""",
                (subscription_id, now),
            )
            rows = db.execute(
                """SELECT d.delivery_id, d.event_seq, d.attempt_count, i.envelope_json,
                          s.lease_seconds
                   FROM delivery d
                   JOIN inbox_event i ON i.event_seq=d.event_seq
                   JOIN subscription s ON s.subscription_id=d.subscription_id
                   WHERE d.subscription_id=? AND d.state='READY' AND d.available_at<=?
                   ORDER BY d.event_seq LIMIT ?""",
                (subscription_id, now, max(1, min(limit, 100))),
            ).fetchall()
            claimed: list[dict[str, Any]] = []
            for row in rows:
                token = uuid.uuid4().hex
                effective_lease = lease_seconds if lease_seconds > 0 else int(row["lease_seconds"])
                lease_until = now + effective_lease * 1000
                db.execute(
                    """UPDATE delivery
                       SET state='LEASED', attempt_count=attempt_count+1, lease_owner=?,
                           lease_token=?, lease_until=?
                       WHERE delivery_id=? AND state='READY'""",
                    (instance_id, token, lease_until, row["delivery_id"]),
                )
                claimed.append(
                    {
                        "deliveryId": row["delivery_id"],
                        "leaseToken": token,
                        "leaseUntil": lease_until,
                        "attempt": int(row["attempt_count"]) + 1,
                        "event": json.loads(row["envelope_json"]),
                    }
                )
            db.commit()
            return claimed
        except Exception:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

    async def renew(self, delivery_id: str, lease_token: str, lease_seconds: int) -> dict[str, Any] | None:
        return await self._run(self._renew_sync, delivery_id, lease_token, lease_seconds)

    def _renew_sync(self, delivery_id: str, lease_token: str, lease_seconds: int) -> dict[str, Any] | None:
        now = _now_ms()
        lease_until = now + lease_seconds * 1000
        with self._connect() as db:
            cursor = db.execute(
                """UPDATE delivery SET lease_until=?
                   WHERE delivery_id=? AND state='LEASED' AND lease_token=? AND lease_until>?""",
                (lease_until, delivery_id, lease_token, now),
            )
            if cursor.rowcount != 1:
                return None
        return {"deliveryId": delivery_id, "leaseUntil": lease_until}

    async def ack(self, delivery_id: str, lease_token: str) -> bool:
        return bool(await self._run(self._ack_sync, delivery_id, lease_token))

    def _ack_sync(self, delivery_id: str, lease_token: str) -> bool:
        now = _now_ms()
        with self._connect() as db:
            cursor = db.execute(
                """UPDATE delivery SET state='ACKED', acked_at=?, lease_until=0
                   WHERE delivery_id=? AND state='LEASED' AND lease_token=? AND lease_until>?""",
                (now, delivery_id, lease_token, now),
            )
            if cursor.rowcount == 1:
                return True
            row = db.execute(
                "SELECT 1 FROM delivery WHERE delivery_id=? AND state='ACKED' AND lease_token=?",
                (delivery_id, lease_token),
            ).fetchone()
        return row is not None

    async def nack(self, delivery_id: str, lease_token: str, error: str, retry_seconds: int = 5) -> bool:
        return bool(await self._run(self._nack_sync, delivery_id, lease_token, error, retry_seconds))

    def _nack_sync(self, delivery_id: str, lease_token: str, error: str, retry_seconds: int) -> bool:
        now = _now_ms()
        with self._connect() as db:
            cursor = db.execute(
                """UPDATE delivery SET
                       state=CASE WHEN attempt_count >= (
                           SELECT max_attempts FROM subscription s
                           WHERE s.subscription_id=delivery.subscription_id
                       ) THEN 'DEAD' ELSE 'READY' END,
                       available_at=?, lease_owner='', lease_token='', lease_until=0, last_error=?
                   WHERE delivery_id=? AND state='LEASED' AND lease_token=? AND lease_until>?""",
                (
                    now + max(0, retry_seconds) * 1000,
                    error[:4000],
                    delivery_id,
                    lease_token,
                    now,
                ),
            )
        return cursor.rowcount == 1

    async def stats(self) -> dict[str, int]:
        return await self._run(self._stats_sync)

    async def get_connection_state(self, connection_id: str, key: str) -> str:
        return str(await self._run(self._get_connection_state_sync, connection_id, key))

    def _get_connection_state_sync(self, connection_id: str, key: str) -> str:
        with self._connect() as db:
            row = db.execute(
                "SELECT state_value FROM connection_state WHERE connection_id=? AND state_key=?",
                (connection_id, key),
            ).fetchone()
        return str(row["state_value"]) if row is not None else ""

    async def set_connection_state(self, connection_id: str, key: str, value: str) -> None:
        await self._run(self._set_connection_state_sync, connection_id, key, value)

    def _set_connection_state_sync(self, connection_id: str, key: str, value: str) -> None:
        with self._connect() as db:
            db.execute(
                """INSERT INTO connection_state(connection_id, state_key, state_value, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(connection_id, state_key) DO UPDATE SET
                       state_value=excluded.state_value, updated_at=excluded.updated_at""",
                (connection_id, key, value, _now_ms()),
            )

    async def connection_states(self) -> dict[str, dict[str, str]]:
        return await self._run(self._connection_states_sync)

    def _connection_states_sync(self) -> dict[str, dict[str, str]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT connection_id, state_key, state_value FROM connection_state ORDER BY connection_id, state_key"
            ).fetchall()
        states: dict[str, dict[str, str]] = {}
        for row in rows:
            states.setdefault(str(row["connection_id"]), {})[str(row["state_key"])] = str(row["state_value"])
        return states

    def _stats_sync(self) -> dict[str, int]:
        now = _now_ms()
        with self._connect() as db:
            rows = db.execute("SELECT state, COUNT(*) AS count FROM delivery GROUP BY state").fetchall()
            accepted = db.execute("SELECT COUNT(*) AS count FROM inbox_event").fetchone()
            conflicts = db.execute("SELECT COALESCE(SUM(conflict_count), 0) AS count FROM inbox_event").fetchone()
            raw_failed = db.execute(
                "SELECT COUNT(*) AS count FROM raw_delivery "
                "WHERE normalize_state IN ('NORMALIZE_RETRY', 'ADAPTER_DEAD')"
            ).fetchone()
            oldest = db.execute(
                "SELECT MIN(created_at) AS created_at FROM delivery WHERE state IN ('READY', 'LEASED')"
            ).fetchone()
            last_ack = db.execute("SELECT COALESCE(MAX(acked_at), 0) AS acked_at FROM delivery").fetchone()
        out = {str(row["state"]).casefold(): int(row["count"]) for row in rows}
        out["events_accepted_total"] = int(accepted["count"])
        out["conflicts"] = int(conflicts["count"])
        out["raw_failed"] = int(raw_failed["count"])
        out["consumer_backlog"] = out.get("ready", 0) + out.get("leased", 0)
        out["active_leases"] = out.get("leased", 0)
        created_at = oldest["created_at"]
        out["oldest_unacked_age_ms"] = max(0, now - int(created_at)) if created_at is not None else 0
        out["consumer_last_ack_ms"] = int(last_ack["acked_at"])
        return out
