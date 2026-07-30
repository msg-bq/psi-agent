from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from psi_agent.eventd.schema import CloudEvent, EventConflictError, Subscription
from psi_agent.eventd.store import EventStore


def _event(data: dict[str, object] | None = None) -> CloudEvent:
    return CloudEvent(
        "1.0",
        "event-1",
        "feishu://tenant/app/approval",
        "approval.status.changed",
        data or {"approval_code": "expense", "status": "APPROVED"},
    )


@pytest.mark.anyio
async def test_ingest_deduplicate_conflict_and_ack(tmp_path: Path) -> None:
    store = EventStore(str(tmp_path / "events.sqlite3"))
    await store.initialize()
    await store.upsert_subscription(Subscription(id="finance", max_attempts=2))

    status, event_seq = await store.ingest(_event(), ["finance"])
    assert status == "created"
    duplicate, duplicate_seq = await store.ingest(_event(), ["finance"])
    assert (duplicate, duplicate_seq) == ("duplicate", event_seq)
    with pytest.raises(EventConflictError):
        await store.ingest(_event({"approval_code": "expense", "status": "REJECTED"}), ["finance"])

    claimed = await store.claim(subscription_id="finance", instance_id="consumer-1", limit=1, lease_seconds=60)
    assert len(claimed) == 1
    delivery = claimed[0]
    assert delivery["attempt"] == 1
    assert await store.ack(delivery["deliveryId"], delivery["leaseToken"])
    assert await store.ack(delivery["deliveryId"], delivery["leaseToken"])
    assert not await store.ack(delivery["deliveryId"], "stale")
    assert await store.claim(subscription_id="finance", instance_id="consumer-1", limit=1, lease_seconds=60) == []
    stats = await store.stats()
    assert stats["events_accepted_total"] == 1
    assert stats["consumer_backlog"] == 0
    assert stats["consumer_last_ack_ms"] > 0


@pytest.mark.anyio
async def test_nack_releases_with_new_lease_and_dead_letters(tmp_path: Path) -> None:
    store = EventStore(str(tmp_path / "events.sqlite3"))
    await store.initialize()
    await store.upsert_subscription(Subscription(id="finance", max_attempts=2))
    await store.ingest(_event(), ["finance"])
    first = (await store.claim(subscription_id="finance", instance_id="one", limit=1, lease_seconds=60))[0]
    assert await store.nack(first["deliveryId"], first["leaseToken"], "retry", retry_seconds=0)
    second = (await store.claim(subscription_id="finance", instance_id="two", limit=1, lease_seconds=60))[0]
    assert second["leaseToken"] != first["leaseToken"]
    assert second["attempt"] == 2
    assert not await store.renew(first["deliveryId"], first["leaseToken"], 60)
    assert await store.nack(second["deliveryId"], second["leaseToken"], "poison", retry_seconds=0)
    assert await store.claim(subscription_id="finance", instance_id="three", limit=1, lease_seconds=60) == []
    stats = await store.stats()
    assert stats["dead"] == 1


@pytest.mark.anyio
async def test_expired_lease_rejects_control_and_stale_token_cannot_ack_new_lease(tmp_path: Path) -> None:
    db_path = tmp_path / "events.sqlite3"
    store = EventStore(str(db_path))
    await store.initialize()
    await store.upsert_subscription(Subscription(id="finance", max_attempts=3))
    await store.ingest(_event(), ["finance"])
    first = (await store.claim(subscription_id="finance", instance_id="one", limit=1, lease_seconds=60))[0]
    with sqlite3.connect(db_path) as db:
        db.execute("UPDATE delivery SET lease_until=0 WHERE delivery_id=?", (first["deliveryId"],))
    assert not await store.renew(first["deliveryId"], first["leaseToken"], 60)
    assert not await store.ack(first["deliveryId"], first["leaseToken"])
    assert not await store.nack(first["deliveryId"], first["leaseToken"], "stale", retry_seconds=0)
    restarted = EventStore(str(db_path))
    await restarted.initialize()
    second = (await restarted.claim(subscription_id="finance", instance_id="two", limit=1, lease_seconds=60))[0]
    assert second["leaseToken"] != first["leaseToken"]
    assert not await restarted.ack(first["deliveryId"], first["leaseToken"])
    assert await restarted.ack(second["deliveryId"], second["leaseToken"])


@pytest.mark.anyio
async def test_raw_delivery_survives_enrichment_failure(tmp_path: Path) -> None:
    store = EventStore(str(tmp_path / "events.sqlite3"))
    await store.initialize()
    receipt = await store.receive_raw(
        provider="feishu",
        connection_id="finance-feishu",
        transport="websocket",
        provider_event_id="provider-1",
        raw_payload={"event": {"instance_code": "instance-1"}},
    )
    await store.set_raw_state(receipt, "NORMALIZE_RETRY", "temporary failure")
    pending = await store.pending_raw("finance-feishu")
    assert pending[0]["receipt_id"] == receipt
    assert pending[0]["raw_payload"]["event"]["instance_code"] == "instance-1"


@pytest.mark.anyio
async def test_stale_normalizing_raw_delivery_is_recovered(tmp_path: Path) -> None:
    store = EventStore(str(tmp_path / "events.sqlite3"))
    await store.initialize()
    receipt = await store.receive_raw(
        provider="feishu",
        connection_id="finance-feishu",
        transport="websocket",
        provider_event_id="provider-1",
        raw_payload={"event": {"instance_code": "instance-1"}},
    )
    await store.set_raw_state(receipt, "NORMALIZING")
    assert await store.pending_raw("finance-feishu", stale_after_seconds=3600) == []
    restarted = EventStore(store.path)
    await restarted.initialize()
    pending = await restarted.pending_raw("finance-feishu", stale_after_seconds=0)
    assert [row["receipt_id"] for row in pending] == [receipt]


@pytest.mark.anyio
async def test_ready_requires_initialized_writable_schema(tmp_path: Path) -> None:
    store = EventStore(str(tmp_path / "events.sqlite3"))
    assert not await store.ready()
    await store.initialize()
    assert await store.ready()


@pytest.mark.anyio
async def test_initialize_migrates_pre_normalize_timestamp_database(tmp_path: Path) -> None:
    db_path = tmp_path / "events.sqlite3"
    with sqlite3.connect(db_path) as db:
        db.execute(
            """CREATE TABLE raw_delivery (
                   receipt_id TEXT PRIMARY KEY, provider TEXT NOT NULL,
                   connection_id TEXT NOT NULL, transport TEXT NOT NULL,
                   provider_event_id TEXT NOT NULL, raw_payload TEXT NOT NULL,
                   received_at INTEGER NOT NULL, normalize_state TEXT NOT NULL,
                   normalize_attempts INTEGER NOT NULL DEFAULT 0,
                   last_error TEXT NOT NULL DEFAULT ''
               )"""
        )
    store = EventStore(str(db_path))
    await store.initialize()
    with sqlite3.connect(db_path) as db:
        columns = {str(row[1]) for row in db.execute("PRAGMA table_info(raw_delivery)")}
    assert "normalize_started_at" in columns
