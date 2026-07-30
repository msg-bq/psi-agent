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
        "shop://orders",
        "order.paid",
        data or {"order_id": "1001", "status": "paid"},
    )


@pytest.mark.anyio
async def test_ingest_deduplicate_conflict_and_ack(tmp_path: Path) -> None:
    store = EventStore(str(tmp_path / "events.sqlite3"))
    await store.initialize()
    await store.upsert_subscription(Subscription(id="orders", max_attempts=2))

    status, event_seq = await store.ingest(_event(), ["orders"])
    assert status == "created"
    duplicate, duplicate_seq = await store.ingest(_event(), ["orders"])
    assert (duplicate, duplicate_seq) == ("duplicate", event_seq)
    with pytest.raises(EventConflictError):
        await store.ingest(_event({"order_id": "1001", "status": "refunded"}), ["orders"])

    claimed = await store.claim(subscription_id="orders", instance_id="consumer-1", limit=1, lease_seconds=60)
    assert len(claimed) == 1
    delivery = claimed[0]
    assert delivery["attempt"] == 1
    assert await store.ack(delivery["deliveryId"], delivery["leaseToken"])
    assert await store.ack(delivery["deliveryId"], delivery["leaseToken"])
    assert not await store.ack(delivery["deliveryId"], "stale")
    assert await store.claim(subscription_id="orders", instance_id="consumer-1", limit=1, lease_seconds=60) == []
    stats = await store.stats()
    assert stats["events_accepted_total"] == 1
    assert stats["consumer_backlog"] == 0
    assert stats["consumer_last_ack_ms"] > 0


@pytest.mark.anyio
async def test_nack_releases_with_new_lease_and_dead_letters(tmp_path: Path) -> None:
    store = EventStore(str(tmp_path / "events.sqlite3"))
    await store.initialize()
    await store.upsert_subscription(Subscription(id="orders", max_attempts=2))
    await store.ingest(_event(), ["orders"])
    first = (await store.claim(subscription_id="orders", instance_id="one", limit=1, lease_seconds=60))[0]
    assert await store.nack(first["deliveryId"], first["leaseToken"], "retry", retry_seconds=0)
    second = (await store.claim(subscription_id="orders", instance_id="two", limit=1, lease_seconds=60))[0]
    assert second["leaseToken"] != first["leaseToken"]
    assert second["attempt"] == 2
    assert not await store.renew(first["deliveryId"], first["leaseToken"], 60)
    assert await store.nack(second["deliveryId"], second["leaseToken"], "poison", retry_seconds=0)
    assert await store.claim(subscription_id="orders", instance_id="three", limit=1, lease_seconds=60) == []
    stats = await store.stats()
    assert stats["dead"] == 1


@pytest.mark.anyio
async def test_expired_lease_rejects_control_and_stale_token_cannot_ack_new_lease(tmp_path: Path) -> None:
    db_path = tmp_path / "events.sqlite3"
    store = EventStore(str(db_path))
    await store.initialize()
    await store.upsert_subscription(Subscription(id="orders", max_attempts=3))
    await store.ingest(_event(), ["orders"])
    first = (await store.claim(subscription_id="orders", instance_id="one", limit=1, lease_seconds=60))[0]
    with sqlite3.connect(db_path) as db:
        db.execute("UPDATE delivery SET lease_until=0 WHERE delivery_id=?", (first["deliveryId"],))
    assert not await store.renew(first["deliveryId"], first["leaseToken"], 60)
    assert not await store.ack(first["deliveryId"], first["leaseToken"])
    assert not await store.nack(first["deliveryId"], first["leaseToken"], "stale", retry_seconds=0)
    restarted = EventStore(str(db_path))
    await restarted.initialize()
    second = (await restarted.claim(subscription_id="orders", instance_id="two", limit=1, lease_seconds=60))[0]
    assert second["leaseToken"] != first["leaseToken"]
    assert not await restarted.ack(first["deliveryId"], first["leaseToken"])
    assert await restarted.ack(second["deliveryId"], second["leaseToken"])


@pytest.mark.anyio
async def test_ready_requires_initialized_writable_schema(tmp_path: Path) -> None:
    store = EventStore(str(tmp_path / "events.sqlite3"))
    assert not await store.ready()
    await store.initialize()
    assert await store.ready()
