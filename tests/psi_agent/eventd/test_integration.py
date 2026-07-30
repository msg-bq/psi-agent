from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

import anyio
import pytest
from aiohttp import ClientSession, web

from psi_agent.eventd.consumer import EventConsumerWorker
from psi_agent.eventd.schema import CloudEvent, Hook, Subscription
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
async def test_consumer_claims_dispatches_and_acks(tmp_path: Path) -> None:
    acked = anyio.Event()

    class AckStore(EventStore):
        async def ack(self, delivery_id: str, lease_token: str) -> bool:
            result = await super().ack(delivery_id, lease_token)
            if result:
                acked.set()
            return result

    store = AckStore(str(tmp_path / "events.sqlite3"))
    subscription = Subscription(id="orders", types=("order.paid",))
    service = EventService(store, (subscription,))
    await service.initialize()
    eventd_runner, eventd_url = await _start(build_eventd_app(service, api_token="secret"))

    received: list[dict[str, Any]] = []

    async def receive(request: web.Request) -> web.Response:
        body = await request.json()
        received.append(body)
        return web.json_response(
            {"ok": True, "matched": 1, "fired": ["finance-handler"], "failed": {}, "duplicate": False}
        )

    session_app = web.Application()
    session_app.router.add_post("/events", receive)
    session_runner, session_url = await _start(session_app)
    await service.accept(
        CloudEvent(
            "1.0",
            "event-1",
            "shop://orders",
            "order.paid",
            {"order_id": "1001", "status": "paid"},
        )
    )
    worker = EventConsumerWorker(
        daemon_endpoint=eventd_url,
        subscription_id="orders",
        session_socket=session_url,
        renew_every_seconds=1,
        lease_seconds=3,
        wait_seconds=1,
        api_token="secret",
    )
    try:
        async with anyio.create_task_group() as tg:
            tg.start_soon(worker.run)
            with anyio.fail_after(5):
                await acked.wait()
            tg.cancel_scope.cancel()
    finally:
        with anyio.CancelScope(shield=True):
            await session_runner.cleanup()
            await eventd_runner.cleanup()

    assert received[0]["source"] == "eventd"
    assert received[0]["event"] == "order.paid"
    assert received[0]["idempotency_key"] == "shop://orders|event-1"
    assert received[0]["routing"]["delivery_id"].startswith("delivery_")
    assert received[0]["routing"]["event_id"] == "event-1"


@pytest.mark.anyio
async def test_canonical_and_url_only_ingress_share_durable_queue(tmp_path: Path) -> None:
    store = EventStore(str(tmp_path / "events.sqlite3"))
    subscription = Subscription(id="orders", types=("order.received", "order.paid"))
    hook = Hook(
        id="orders",
        token="hook-secret",
        source="webhook://orders",
        type="order.received",
        id_header="X-Event-Id",
    )
    service = EventService(store, (subscription,), (hook,))
    await service.initialize()
    runner, base = await _start(build_eventd_app(service, api_token="api-secret"))
    try:
        async with ClientSession() as session:
            async with session.post(
                f"{base}/hooks/orders/hook-secret",
                json={"order_id": "1001"},
                headers={"X-Event-Id": "hook-event-1"},
            ) as response:
                assert response.status == 202
            async with session.post(
                f"{base}/v1/events",
                json={
                    "specversion": "1.0",
                    "id": "canonical-event-1",
                    "source": "shop://orders",
                    "type": "order.paid",
                    "data": {"order_id": "1002"},
                },
                headers={"Authorization": "Bearer api-secret"},
            ) as response:
                assert response.status == 202
    finally:
        with anyio.CancelScope(shield=True):
            await runner.cleanup()

    first = await store.claim(subscription_id="orders", instance_id="test", limit=2, lease_seconds=60)
    assert [delivery["event"]["id"] for delivery in first] == ["hook-event-1", "canonical-event-1"]
    assert first[0]["event"]["data"] == {"order_id": "1001"}
