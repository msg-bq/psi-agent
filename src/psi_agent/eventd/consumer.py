"""Lease-based Event Daemon consumer that dispatches into Session ``/events``."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

import aiohttp
import anyio
from aiohttp import ClientTimeout
from loguru import logger

from psi_agent._sockets import resolve_connector_and_endpoint
from psi_agent.channel._core import ChannelCore
from psi_agent.eventd.schema import CloudEvent, cloud_event_to_session_envelope


class ConsumerError(RuntimeError):
    """A durable delivery could not be safely completed."""


@dataclass(slots=True)
class EventConsumerWorker:
    daemon_endpoint: str
    subscription_id: str
    session_socket: str
    instance_id: str = ""
    renew_every_seconds: int = 20
    lease_seconds: int = 60
    wait_seconds: int = 20
    api_token: str = ""
    routing: dict[str, Any] | None = None

    async def run(self) -> None:
        instance_id = self.instance_id.strip() or f"psi-agent/{uuid.uuid4()}"
        connector, base = resolve_connector_and_endpoint(self.daemon_endpoint, path_prefix="")
        headers = {"Authorization": f"Bearer {self.api_token}"} if self.api_token else {}
        timeout = ClientTimeout(total=None)
        async with (
            aiohttp.ClientSession(connector=connector, headers=headers, timeout=timeout) as http,
            ChannelCore(self.session_socket, interval=0) as core,
        ):
            logger.info(f"Event consumer started subscription={self.subscription_id!r} instance={instance_id!r}")
            failures = 0
            while True:
                try:
                    deliveries = await self._claim(http, base, instance_id)
                    for delivery in deliveries:
                        await self._process(http, base, core, delivery)
                    failures = 0
                except (aiohttp.ClientError, ConsumerError, OSError) as e:
                    failures += 1
                    delay = min(30.0, float(2 ** min(failures - 1, 5)))
                    logger.warning(f"Event consumer transport failure; retrying in {delay:.1f}s: {e!r}")
                    await anyio.sleep(delay)

    async def _claim(self, http: aiohttp.ClientSession, base: str, instance_id: str) -> list[dict[str, Any]]:
        path = f"/internal/v1/subscriptions/{self.subscription_id}/claim"
        body: dict[str, object] = {
            "instanceId": instance_id,
            "limit": 1,
            "leaseSeconds": self.lease_seconds,
            "waitSeconds": self.wait_seconds,
        }
        data = await self._post_json(http, base + path, body)
        deliveries = data.get("deliveries", [])
        if not isinstance(deliveries, list) or any(not isinstance(item, dict) for item in deliveries):
            raise ConsumerError("claim response deliveries must be a list of objects")
        return cast(list[dict[str, Any]], deliveries)

    async def _process(
        self,
        http: aiohttp.ClientSession,
        base: str,
        core: ChannelCore,
        delivery: dict[str, Any],
    ) -> None:
        delivery_id = str(delivery.get("deliveryId") or "")
        token = str(delivery.get("leaseToken") or "")
        if not delivery_id or not token:
            raise ConsumerError("delivery is missing deliveryId or leaseToken")
        result: dict[str, object] | None = None
        try:
            event = CloudEvent.parse(delivery.get("event"))
            event_routing = dict(self.routing or {})
            event_routing.update(
                {
                    "delivery_id": delivery_id,
                    "event_source": event.source,
                    "event_id": event.id,
                }
            )
            async with anyio.create_task_group() as tg:
                tg.start_soon(self._renew_loop, http, base, delivery_id, token)
                result = await core.post_event(cloud_event_to_session_envelope(event, routing=event_routing))
                tg.cancel_scope.cancel()
        except Exception as e:
            logger.warning(f"Delivery {delivery_id} dispatch failed: {e!r}")
            await self._nack(http, base, delivery_id, token, str(e))
            return

        if result is None:
            await self._nack(http, base, delivery_id, token, "Session returned no result")
            return
        fired = result.get("fired")
        failed = result.get("failed")
        duplicate = result.get("duplicate") is True
        succeeded = result.get("ok") is True and isinstance(fired, list) and bool(fired) and not failed
        if succeeded or (result.get("ok") is True and duplicate):
            await self._control(http, base, delivery_id, "ack", {"leaseToken": token})
            logger.info(f"Delivery {delivery_id} ACKed duplicate={duplicate}")
            return
        matched = result.get("matched")
        reason = f"Session did not complete delivery: matched={matched!r} fired={fired!r} failed={failed!r}"
        await self._nack(http, base, delivery_id, token, reason)

    async def _renew_loop(
        self,
        http: aiohttp.ClientSession,
        base: str,
        delivery_id: str,
        token: str,
    ) -> None:
        while True:
            await anyio.sleep(self.renew_every_seconds)
            await self._control(
                http,
                base,
                delivery_id,
                "renew",
                {"leaseToken": token, "leaseSeconds": self.lease_seconds},
            )
            logger.debug(f"Delivery {delivery_id} lease renewed")

    async def _nack(
        self,
        http: aiohttp.ClientSession,
        base: str,
        delivery_id: str,
        token: str,
        error: str,
    ) -> None:
        try:
            await self._control(
                http,
                base,
                delivery_id,
                "nack",
                {"leaseToken": token, "error": error, "retrySeconds": 5},
            )
        except ConsumerError as e:
            logger.warning(f"Delivery {delivery_id} NACK rejected: {e}")

    async def _control(
        self,
        http: aiohttp.ClientSession,
        base: str,
        delivery_id: str,
        action: str,
        body: Mapping[str, object],
    ) -> dict[str, Any]:
        return await self._post_json(http, f"{base}/internal/v1/deliveries/{delivery_id}/{action}", body)

    @staticmethod
    async def _post_json(
        http: aiohttp.ClientSession,
        url: str,
        body: Mapping[str, object],
    ) -> dict[str, Any]:
        async with http.post(url, json=body) as response:
            try:
                raw = await response.json()
            except Exception as e:
                raise ConsumerError(f"{url} returned invalid JSON: {e}") from e
            if not isinstance(raw, dict):
                raise ConsumerError(f"{url} response must be an object")
            if response.status >= 400:
                raise ConsumerError(f"{url} HTTP {response.status}: {raw.get('error')}")
            return cast(dict[str, Any], raw)
