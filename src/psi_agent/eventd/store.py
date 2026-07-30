"""SQLite persistence for the generic Event Daemon inbox and leases."""

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
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name IN ('inbox_event', 'subscription', 'delivery')"
                )
            }
            if tables != {"inbox_event", "subscription", "delivery"}:
                return False
            db.execute("BEGIN IMMEDIATE")
            db.execute("SELECT COUNT(*) FROM inbox_event")
            db.rollback()
        return True

    async def upsert_subscription(self, subscription: Subscription) -> None:
        await self._run(self._upsert_subscription_sync, subscription)

    def _upsert_subscription_sync(self, subscription: Subscription) -> None:
        with self._connect() as db:
            db.execute(
                """INSERT INTO subscription(
                       subscription_id, filter_json, lease_seconds, max_attempts, updated_at
                   ) VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(subscription_id) DO UPDATE SET
                       filter_json=excluded.filter_json,
                       lease_seconds=excluded.lease_seconds,
                       max_attempts=excluded.max_attempts,
                       updated_at=excluded.updated_at""",
                (
                    subscription.id,
                    json.dumps(subscription.filter_dict(), ensure_ascii=False, sort_keys=True),
                    subscription.lease_seconds,
                    subscription.max_attempts,
                    _now_ms(),
                ),
            )

    async def ingest(self, event: CloudEvent, subscription_ids: list[str]) -> tuple[str, int]:
        return await self._run(self._ingest_sync, event, subscription_ids)

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
            rows = db.execute(
                """SELECT d.delivery_id, d.attempt_count, i.envelope_json, s.lease_seconds
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
                cursor = db.execute(
                    """UPDATE delivery
                       SET state='LEASED', attempt_count=attempt_count+1, lease_owner=?,
                           lease_token=?, lease_until=?
                       WHERE delivery_id=? AND state='READY'""",
                    (instance_id, token, lease_until, row["delivery_id"]),
                )
                if cursor.rowcount != 1:
                    continue
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
                (now + max(0, retry_seconds) * 1000, error[:4000], delivery_id, lease_token, now),
            )
        return cursor.rowcount == 1

    async def stats(self) -> dict[str, int]:
        return await self._run(self._stats_sync)

    def _stats_sync(self) -> dict[str, int]:
        now = _now_ms()
        with self._connect() as db:
            rows = db.execute("SELECT state, COUNT(*) AS count FROM delivery GROUP BY state").fetchall()
            accepted = db.execute("SELECT COUNT(*) AS count FROM inbox_event").fetchone()
            conflicts = db.execute("SELECT COALESCE(SUM(conflict_count), 0) AS count FROM inbox_event").fetchone()
            oldest = db.execute(
                "SELECT MIN(created_at) AS created_at FROM delivery WHERE state IN ('READY', 'LEASED')"
            ).fetchone()
            last_ack = db.execute("SELECT COALESCE(MAX(acked_at), 0) AS acked_at FROM delivery").fetchone()
        out = {str(row["state"]).casefold(): int(row["count"]) for row in rows}
        out["events_accepted_total"] = int(accepted["count"])
        out["conflicts"] = int(conflicts["count"])
        out["consumer_backlog"] = out.get("ready", 0) + out.get("leased", 0)
        out["active_leases"] = out.get("leased", 0)
        created_at = oldest["created_at"]
        out["oldest_unacked_age_ms"] = max(0, now - int(created_at)) if created_at is not None else 0
        out["consumer_last_ack_ms"] = int(last_ack["acked_at"])
        return out
