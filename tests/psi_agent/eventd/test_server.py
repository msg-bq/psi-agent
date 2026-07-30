from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

import anyio
import pytest
from aiohttp import ClientSession, web

from psi_agent.eventd.schema import Subscription
from psi_agent.eventd.server import EventService, build_eventd_app
from psi_agent.eventd.store import EventStore


async def _start(app: web.Application) -> tuple[web.AppRunner, str]:
    runner = web.AppRunner(app)
    await runner.setup()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    site = web.SockSite(runner, sock)
    await site.start()
    return runner, f"http://127.0.0.1:{port}"


@pytest.mark.anyio
async def test_ingress_reports_matching_subscriptions_and_keeps_unmatched_event(tmp_path: Path) -> None:
    store = EventStore(str(tmp_path / "events.sqlite3"))
    service = EventService(store, (Subscription(id="orders", types=("order.paid",)),))
    await service.initialize()
    runner, base = await _start(build_eventd_app(service))
    try:
        async with ClientSession() as session:
            async with session.post(
                f"{base}/v1/events",
                json={
                    "specversion": "1.0",
                    "id": "event-matched",
                    "source": "shop://orders",
                    "type": "order.paid",
                    "data": {"order_id": "1001"},
                },
            ) as response:
                assert response.status == 202
                assert (await response.json())["matchedSubscriptions"] == 1
            async with session.post(
                f"{base}/v1/events",
                json={
                    "specversion": "1.0",
                    "id": "event-unmatched",
                    "source": "shop://orders",
                    "type": "order.cancelled",
                    "data": {"order_id": "1002"},
                },
            ) as response:
                assert response.status == 202
                assert (await response.json())["matchedSubscriptions"] == 0
    finally:
        with anyio.CancelScope(shield=True):
            await runner.cleanup()

    assert (await store.stats())["events_accepted_total"] == 2
    deliveries = await store.claim(
        subscription_id="orders",
        instance_id="test",
        limit=10,
        lease_seconds=60,
    )
    assert [delivery["event"]["id"] for delivery in deliveries] == ["event-matched"]


@pytest.mark.anyio
async def test_subscription_lookup_and_unknown_claim_are_explicit(tmp_path: Path) -> None:
    store = EventStore(str(tmp_path / "events.sqlite3"))
    subscription = Subscription(
        id="orders",
        source_prefix="shop://",
        types=("order.paid",),
        lease_seconds=45,
        max_attempts=7,
    )
    service = EventService(store, (subscription,))
    await service.initialize()
    runner, base = await _start(build_eventd_app(service, api_token="secret"))
    headers = {"Authorization": "Bearer secret"}
    try:
        async with ClientSession() as session:
            async with session.get(f"{base}/internal/v1/subscriptions/orders", headers=headers) as response:
                assert response.status == 200
                assert await response.json() == {
                    "id": "orders",
                    "filter": {"sourcePrefix": "shop://", "types": ["order.paid"]},
                    "leaseSeconds": 45,
                    "maxAttempts": 7,
                }
            async with session.get(f"{base}/internal/v1/subscriptions/missing", headers=headers) as response:
                assert response.status == 404
                assert await response.json() == {"error": "subscription not found"}
            async with session.post(
                f"{base}/internal/v1/subscriptions/missing/claim",
                headers=headers,
                json={"instanceId": "consumer-1"},
            ) as response:
                assert response.status == 404
                assert await response.json() == {"error": "subscription not found"}
    finally:
        with anyio.CancelScope(shield=True):
            await runner.cleanup()


@pytest.mark.anyio
async def test_claim_allows_configured_lease_fallback_and_rejects_negative_override(tmp_path: Path) -> None:
    class RecordingStore(EventStore):
        def __init__(self, path: str) -> None:
            super().__init__(path)
            self.claimed_lease_seconds: list[int] = []

        async def claim(
            self,
            *,
            subscription_id: str,
            instance_id: str,
            limit: int,
            lease_seconds: int,
        ) -> list[dict[str, Any]]:
            self.claimed_lease_seconds.append(lease_seconds)
            return []

    store = RecordingStore(str(tmp_path / "events.sqlite3"))
    service = EventService(store, (Subscription(id="orders", lease_seconds=45),))
    runner, base = await _start(build_eventd_app(service))
    try:
        async with ClientSession() as session:
            claim_url = f"{base}/internal/v1/subscriptions/orders/claim"
            for body in (
                {"instanceId": "consumer-1"},
                {"instanceId": "consumer-1", "leaseSeconds": 0},
                {"instanceId": "consumer-1", "leaseSeconds": 9},
            ):
                async with session.post(claim_url, json=body) as response:
                    assert response.status == 200
            async with session.post(
                claim_url,
                json={"instanceId": "consumer-1", "leaseSeconds": -1},
            ) as response:
                assert response.status == 400
                assert await response.json() == {"error": "leaseSeconds must be a non-negative integer"}
            for field, value, error in (
                ("limit", 0, "limit must be between 1 and 100"),
                ("limit", 101, "limit must be between 1 and 100"),
                ("waitSeconds", -1, "waitSeconds must be between 0 and 30"),
                ("waitSeconds", 31, "waitSeconds must be between 0 and 30"),
            ):
                async with session.post(
                    claim_url,
                    json={"instanceId": "consumer-1", field: value},
                ) as response:
                    assert response.status == 400
                    assert await response.json() == {"error": error}
    finally:
        with anyio.CancelScope(shield=True):
            await runner.cleanup()

    assert store.claimed_lease_seconds == [0, 0, 9]


@pytest.mark.anyio
async def test_openapi_endpoint_describes_the_running_contract(tmp_path: Path) -> None:
    store = EventStore(str(tmp_path / "events.sqlite3"))
    service = EventService(store, (Subscription(id="default"),))
    await service.initialize()
    runner, base = await _start(build_eventd_app(service))
    try:
        async with ClientSession() as session, session.get(f"{base}/openapi.json") as response:
            assert response.status == 200
            document = await response.json()
    finally:
        with anyio.CancelScope(shield=True):
            await runner.cleanup()

    assert document["openapi"] == "3.1.0"
    assert "/openapi.json" in document["paths"]
    assert "/v1/events" in document["paths"]
    assert "/internal/v1/subscriptions/{subscription_id}/claim" in document["paths"]
