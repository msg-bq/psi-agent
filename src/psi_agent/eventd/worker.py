"""Reusable lease worker for Event Daemon provider adapters."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

import aiohttp
import anyio
from loguru import logger

from psi_agent.eventd.client import Delivery, EventdResponseError
from psi_agent.eventd.schema import Subscription

type DeliveryHandler = Callable[[Delivery], Awaitable[None]]


class LeaseClient(Protocol):
    """Client operations required by ``LeaseWorker``."""

    async def get_subscription(self, subscription_id: str) -> Subscription: ...

    async def claim(
        self,
        *,
        subscription_id: str,
        instance_id: str,
        limit: int,
        lease_seconds: int,
        wait_seconds: int,
    ) -> list[Delivery]: ...

    async def renew(self, delivery: Delivery, *, lease_seconds: int) -> None: ...

    async def ack(self, delivery: Delivery) -> None: ...

    async def nack(self, delivery: Delivery, *, error: str, retry_seconds: int = 5) -> None: ...


@dataclass(slots=True)
class LeaseWorker:
    """Claim deliveries and wrap a handler with renewal and final disposition."""

    client: LeaseClient
    subscription_id: str
    handler: DeliveryHandler
    instance_id: str = ""
    renew_every_seconds: float = 20
    lease_seconds: int = 0
    wait_seconds: int = 20
    limit: int = 1
    nack_retry_seconds: int = 5
    initial_backoff_seconds: float = 1
    max_backoff_seconds: float = 30
    _effective_lease_seconds: int = field(init=False, default=0, repr=False)

    def __post_init__(self) -> None:
        if not self.subscription_id.strip():
            raise ValueError("subscription_id must be non-empty")
        if isinstance(self.renew_every_seconds, bool) or self.renew_every_seconds <= 0:
            raise ValueError("renew_every_seconds must be positive")
        if not isinstance(self.lease_seconds, int) or isinstance(self.lease_seconds, bool) or self.lease_seconds < 0:
            raise ValueError("lease_seconds must be a non-negative integer")
        if self.lease_seconds and self.renew_every_seconds >= self.lease_seconds:
            raise ValueError("renew_every_seconds must be less than lease_seconds")
        if (
            not isinstance(self.wait_seconds, int)
            or isinstance(self.wait_seconds, bool)
            or not 0 <= self.wait_seconds <= 30
        ):
            raise ValueError("wait_seconds must be between 0 and 30")
        if not isinstance(self.limit, int) or isinstance(self.limit, bool) or self.limit != 1:
            raise ValueError("LeaseWorker requires limit=1 so every claimed delivery is renewed immediately")
        if (
            not isinstance(self.nack_retry_seconds, int)
            or isinstance(self.nack_retry_seconds, bool)
            or self.nack_retry_seconds < 0
        ):
            raise ValueError("nack_retry_seconds must be a non-negative integer")
        if (
            isinstance(self.initial_backoff_seconds, bool)
            or isinstance(self.max_backoff_seconds, bool)
            or self.initial_backoff_seconds <= 0
            or self.max_backoff_seconds <= 0
        ):
            raise ValueError("backoff durations must be positive")

    async def run(self) -> None:
        instance_id = self.instance_id.strip() or f"psi-agent/{uuid.uuid4()}"
        logger.info(f"Lease worker started subscription={self.subscription_id!r} instance={instance_id!r}")
        failures = 0
        validated = False
        while True:
            try:
                if not validated or self.lease_seconds == 0:
                    subscription = await self.client.get_subscription(self.subscription_id)
                    self._effective_lease_seconds = self.lease_seconds or subscription.lease_seconds
                    if self.renew_every_seconds >= self._effective_lease_seconds:
                        raise ValueError("renew_every_seconds must be less than the effective lease duration")
                    validated = True
                await self.claim_once(instance_id=instance_id)
                failures = 0
            except Exception as e:
                if not self._is_client_failure(e):
                    raise
                failures += 1
                delay = min(
                    self.max_backoff_seconds,
                    self.initial_backoff_seconds * float(2 ** min(failures - 1, 5)),
                )
                logger.warning(f"Lease worker transport failure; retrying in {delay:.1f}s: {e!r}")
                await anyio.sleep(delay)

    async def claim_once(self, *, instance_id: str) -> int:
        deliveries = await self.client.claim(
            subscription_id=self.subscription_id,
            instance_id=instance_id,
            limit=self.limit,
            lease_seconds=self.lease_seconds,
            wait_seconds=self.wait_seconds,
        )
        for delivery in deliveries:
            await self.process(delivery)
        return len(deliveries)

    async def process(self, delivery: Delivery) -> None:
        if self._effective_lease_seconds <= 0:
            raise RuntimeError("LeaseWorker must validate its subscription before processing deliveries")
        async with anyio.create_task_group() as tg:
            tg.start_soon(self._renew_loop, delivery)
            try:
                await self.handler(delivery)
            except Exception as e:
                logger.warning(f"Delivery {delivery.delivery_id} handler failed: {e!r}")
                await self.client.nack(
                    delivery,
                    error=str(e),
                    retry_seconds=self.nack_retry_seconds,
                )
                logger.info(f"Delivery {delivery.delivery_id} NACKed")
            else:
                await self.client.ack(delivery)
                logger.info(f"Delivery {delivery.delivery_id} ACKed")
            finally:
                tg.cancel_scope.cancel()

    async def _renew_loop(self, delivery: Delivery) -> None:
        while True:
            await anyio.sleep(self.renew_every_seconds)
            await self.client.renew(delivery, lease_seconds=self._effective_lease_seconds)
            logger.debug(f"Delivery {delivery.delivery_id} lease renewed")

    @classmethod
    def _is_client_failure(cls, error: Exception) -> bool:
        if isinstance(error, BaseExceptionGroup):
            return bool(error.exceptions) and all(
                isinstance(item, Exception) and cls._is_client_failure(item) for item in error.exceptions
            )
        if isinstance(error, EventdResponseError):
            stale_delivery_lease = error.status == 409 and error.path.startswith("/internal/v1/deliveries/")
            return error.retryable or stale_delivery_lease
        return isinstance(error, (aiohttp.ClientError, OSError))
