from __future__ import annotations

import socket
from pathlib import Path

import anyio
import pytest
from aiohttp import web

from psi_agent.eventd.client import EventdClient, EventdResponseError, EventdSubscriptionMismatchError
from psi_agent.eventd.schema import CloudEvent, Subscription
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
async def test_client_publishes_and_controls_a_delivery(tmp_path: Path) -> None:
    store = EventStore(str(tmp_path / "events.sqlite3"))
    service = EventService(store, (Subscription(id="orders", types=("order.paid",)),))
    await service.initialize()
    runner, base = await _start(build_eventd_app(service, api_token="secret"))
    event = CloudEvent("1.0", "event-1", "shop://orders", "order.paid", {"order_id": "1001"})
    try:
        async with EventdClient(base, "secret") as client:
            accepted = await client.publish(event)
            assert accepted.status == "created"
            assert accepted.event_seq > 0
            assert accepted.matched_subscriptions == 1

            subscription = await client.get_subscription("orders")
            assert subscription == Subscription(id="orders", types=("order.paid",))

            deliveries = await client.claim(
                subscription_id="orders",
                instance_id="adapter-1",
                lease_seconds=3,
                wait_seconds=0,
            )
            assert len(deliveries) == 1
            delivery = deliveries[0]
            assert delivery.event == event
            assert delivery.attempt == 1

            await client.renew(delivery, lease_seconds=3)
            await client.nack(delivery, error="try again", retry_seconds=0)

            retried = await client.claim(
                subscription_id="orders",
                instance_id="adapter-1",
                lease_seconds=3,
                wait_seconds=0,
            )
            assert len(retried) == 1
            assert retried[0].delivery_id == delivery.delivery_id
            assert retried[0].attempt == 2
            await client.ack(retried[0])

            unmatched = await client.publish(
                CloudEvent("1.0", "event-2", "shop://orders", "order.cancelled", {"order_id": "1002"})
            )
            assert unmatched.matched_subscriptions == 0
            with pytest.raises(EventdSubscriptionMismatchError, match="matched no Event Daemon subscription"):
                await client.publish(
                    CloudEvent("1.0", "event-3", "shop://orders", "order.cancelled", {"order_id": "1003"}),
                    require_match=True,
                )

            with pytest.raises(EventdResponseError) as raised:
                await client.get_subscription("missing")
            assert raised.value.status == 404
            assert not raised.value.retryable
    finally:
        with anyio.CancelScope(shield=True):
            await runner.cleanup()

    assert (await store.stats())["acked"] == 1


@pytest.mark.anyio
async def test_client_requires_an_open_context() -> None:
    client = EventdClient("http://127.0.0.1:8765")
    event = CloudEvent("1.0", "event-1", "test://source", "test.event", {})
    with pytest.raises(RuntimeError, match="async context manager"):
        await client.publish(event)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"limit": 0}, "limit must be between 1 and 100"),
        ({"limit": 101}, "limit must be between 1 and 100"),
        ({"wait_seconds": -1}, "wait_seconds must be between 0 and 30"),
        ({"wait_seconds": 31}, "wait_seconds must be between 0 and 30"),
    ],
)
async def test_client_rejects_claim_values_outside_server_contract(
    kwargs: dict[str, int],
    message: str,
) -> None:
    client = EventdClient("http://127.0.0.1:8765")
    with pytest.raises(ValueError, match=message):
        await client.claim(
            subscription_id="events",
            instance_id="adapter-1",
            **kwargs,
        )
