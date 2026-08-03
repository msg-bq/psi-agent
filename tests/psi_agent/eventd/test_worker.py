from __future__ import annotations

from collections.abc import Awaitable, Callable

import anyio
import pytest

from psi_agent.eventd.client import Delivery, EventdResponseError
from psi_agent.eventd.schema import CloudEvent, Subscription
from psi_agent.eventd.worker import LeaseWorker


def _delivery() -> Delivery:
    return Delivery(
        delivery_id="delivery-1",
        lease_token="token-1",
        lease_until=1,
        attempt=1,
        event=CloudEvent("1.0", "event-1", "test://source", "test.event", {"value": 1}),
    )


async def _noop_handler(_delivery: Delivery) -> None:
    await anyio.sleep(0.0001)


class _FakeClient:
    def __init__(self, claim: Callable[[], Awaitable[list[Delivery]]], *, expected_claim_lease: int = 2) -> None:
        self._claim = claim
        self.expected_claim_lease = expected_claim_lease
        self.renewed = anyio.Event()
        self.acked = anyio.Event()
        self.nacked = anyio.Event()
        self.nack_error = ""
        self.actions: list[str] = []

    async def get_subscription(self, subscription_id: str) -> Subscription:
        assert subscription_id == "events"
        self.actions.append("validate")
        return Subscription(id="events", lease_seconds=2)

    async def claim(
        self,
        *,
        subscription_id: str,
        instance_id: str,
        limit: int,
        lease_seconds: int,
        wait_seconds: int,
    ) -> list[Delivery]:
        assert subscription_id == "events"
        assert instance_id
        assert limit == 1
        assert lease_seconds == self.expected_claim_lease
        assert wait_seconds == 0
        return await self._claim()

    async def renew(self, delivery: Delivery, *, lease_seconds: int) -> None:
        assert delivery.delivery_id == "delivery-1"
        assert lease_seconds == 2
        self.actions.append("renew")
        self.renewed.set()

    async def ack(self, delivery: Delivery) -> None:
        assert delivery.delivery_id == "delivery-1"
        self.actions.append("ack-start")
        await self.renewed.wait()
        self.actions.append("ack-done")
        self.acked.set()

    async def nack(self, delivery: Delivery, *, error: str, retry_seconds: int = 5) -> None:
        assert delivery.delivery_id == "delivery-1"
        assert retry_seconds == 5
        self.actions.append("nack-start")
        await self.renewed.wait()
        self.actions.append("nack-done")
        self.nack_error = error
        self.nacked.set()


@pytest.mark.anyio
async def test_worker_renews_until_ack_finishes() -> None:
    claimed = False

    async def claim() -> list[Delivery]:
        nonlocal claimed
        if not claimed:
            claimed = True
            return [_delivery()]
        await anyio.sleep_forever()
        return []

    client = _FakeClient(claim, expected_claim_lease=0)

    async def handle(delivery: Delivery) -> None:
        assert delivery.event.type == "test.event"
        client.actions.append("handle")

    worker = LeaseWorker(
        client=client,
        subscription_id="events",
        handler=handle,
        renew_every_seconds=0.01,
        lease_seconds=0,
        wait_seconds=0,
    )
    async with anyio.create_task_group() as tg:
        tg.start_soon(worker.run)
        with anyio.fail_after(2):
            await client.acked.wait()
        tg.cancel_scope.cancel()

    assert client.actions[:5] == ["validate", "handle", "ack-start", "renew", "ack-done"]


@pytest.mark.anyio
async def test_worker_nacks_a_handler_failure() -> None:
    claimed = False

    async def claim() -> list[Delivery]:
        nonlocal claimed
        if not claimed:
            claimed = True
            return [_delivery()]
        await anyio.sleep_forever()
        return []

    client = _FakeClient(claim)

    async def handle(_delivery: Delivery) -> None:
        raise ValueError("invalid provider payload")

    worker = LeaseWorker(
        client=client,
        subscription_id="events",
        handler=handle,
        renew_every_seconds=0.01,
        lease_seconds=2,
        wait_seconds=0,
    )
    async with anyio.create_task_group() as tg:
        tg.start_soon(worker.run)
        with anyio.fail_after(2):
            await client.nacked.wait()
        tg.cancel_scope.cancel()

    assert client.actions == ["validate", "nack-start", "renew", "nack-done"]
    assert client.nack_error == "invalid provider payload"


@pytest.mark.anyio
async def test_worker_backs_off_after_a_client_failure() -> None:
    attempts = 0
    failed_at = 0.0
    retried_at = 0.0
    retried = anyio.Event()

    async def claim() -> list[Delivery]:
        nonlocal attempts, failed_at, retried_at
        attempts += 1
        if attempts == 1:
            failed_at = anyio.current_time()
            raise EventdResponseError("/claim", 503, "temporarily unavailable")
        retried_at = anyio.current_time()
        retried.set()
        await anyio.sleep_forever()
        return []

    client = _FakeClient(claim)

    async def handle(_delivery: Delivery) -> None:
        raise AssertionError("no delivery was expected")

    worker = LeaseWorker(
        client=client,
        subscription_id="events",
        handler=handle,
        renew_every_seconds=1,
        lease_seconds=2,
        wait_seconds=0,
        initial_backoff_seconds=0.02,
        max_backoff_seconds=0.02,
    )
    async with anyio.create_task_group() as tg:
        tg.start_soon(worker.run)
        with anyio.fail_after(2):
            await retried.wait()
        tg.cancel_scope.cancel()

    assert attempts == 2
    assert retried_at - failed_at >= 0.015


@pytest.mark.anyio
async def test_worker_fails_fast_for_an_unknown_subscription() -> None:
    async def claim() -> list[Delivery]:
        raise AssertionError("claim must not run before subscription validation")

    class MissingSubscriptionClient(_FakeClient):
        async def get_subscription(self, subscription_id: str) -> Subscription:
            raise EventdResponseError(f"/subscriptions/{subscription_id}", 404, "subscription not found")

    client = MissingSubscriptionClient(claim)

    async def handle(_delivery: Delivery) -> None:
        raise AssertionError("handler must not run")

    worker = LeaseWorker(
        client=client,
        subscription_id="events",
        handler=handle,
        renew_every_seconds=1,
        lease_seconds=2,
        wait_seconds=0,
        initial_backoff_seconds=0.01,
    )
    with pytest.raises(EventdResponseError) as raised:
        await worker.run()
    assert raised.value.status == 404


@pytest.mark.anyio
async def test_worker_recovers_from_a_stale_delivery_lease() -> None:
    claims = 0
    retried = anyio.Event()

    async def claim() -> list[Delivery]:
        nonlocal claims
        claims += 1
        if claims == 1:
            return [_delivery()]
        retried.set()
        await anyio.sleep_forever()
        return []

    class StaleAckClient(_FakeClient):
        async def ack(self, delivery: Delivery) -> None:
            raise EventdResponseError(
                f"/internal/v1/deliveries/{delivery.delivery_id}/ack",
                409,
                "stale lease",
            )

    client = StaleAckClient(claim)

    async def handle(_delivery: Delivery) -> None:
        return

    worker = LeaseWorker(
        client=client,
        subscription_id="events",
        handler=handle,
        renew_every_seconds=1,
        lease_seconds=2,
        wait_seconds=0,
        initial_backoff_seconds=0.01,
        max_backoff_seconds=0.01,
    )
    async with anyio.create_task_group() as tg:
        tg.start_soon(worker.run)
        with anyio.fail_after(2):
            await retried.wait()
        tg.cancel_scope.cancel()

    assert claims == 2


@pytest.mark.anyio
async def test_worker_does_not_retry_an_unrelated_conflict() -> None:
    async def claim() -> list[Delivery]:
        raise EventdResponseError("/v1/events", 409, "conflicting content")

    client = _FakeClient(claim)

    async def handle(_delivery: Delivery) -> None:
        raise AssertionError("handler must not run")

    worker = LeaseWorker(
        client=client,
        subscription_id="events",
        handler=handle,
        renew_every_seconds=1,
        lease_seconds=2,
        wait_seconds=0,
        initial_backoff_seconds=0.01,
    )
    with pytest.raises(EventdResponseError) as raised:
        await worker.run()
    assert raised.value.status == 409


def test_worker_rejects_a_batch_it_cannot_renew_safely() -> None:
    async def claim() -> list[Delivery]:
        return []

    with pytest.raises(ValueError, match="requires limit=1"):
        LeaseWorker(
            client=_FakeClient(claim),
            subscription_id="events",
            handler=_noop_handler,
            renew_every_seconds=1,
            lease_seconds=2,
            wait_seconds=0,
            limit=2,
        )


@pytest.mark.anyio
async def test_worker_rechecks_a_subscription_default_before_each_claim() -> None:
    claims = 0

    async def claim() -> list[Delivery]:
        nonlocal claims
        claims += 1
        return []

    class ChangingSubscriptionClient(_FakeClient):
        async def get_subscription(self, subscription_id: str) -> Subscription:
            assert subscription_id == "events"
            self.actions.append("validate")
            lease_seconds = 3 if self.actions.count("validate") == 1 else 1
            return Subscription(id="events", lease_seconds=lease_seconds)

    client = ChangingSubscriptionClient(claim, expected_claim_lease=0)
    worker = LeaseWorker(
        client=client,
        subscription_id="events",
        handler=_noop_handler,
        renew_every_seconds=2,
        lease_seconds=0,
        wait_seconds=0,
    )

    with pytest.raises(ValueError, match="effective lease duration"):
        await worker.run()

    assert claims == 1
    assert client.actions == ["validate", "validate"]
