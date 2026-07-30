"""Reusable HTTP client for Event Daemon ingress and lease operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Self, cast
from urllib.parse import quote

import aiohttp
import anyio
from aiohttp import ClientTimeout

from psi_agent._sockets import resolve_connector_and_endpoint
from psi_agent.eventd.schema import CloudEvent, CloudEventError, Subscription


class EventdClientError(RuntimeError):
    """An Event Daemon response could not be safely interpreted."""


class EventdResponseError(EventdClientError):
    """Event Daemon returned a non-successful HTTP status."""

    def __init__(self, path: str, status: int, detail: str) -> None:
        self.path = path
        self.status = status
        self.detail = detail
        super().__init__(f"{path} HTTP {status}: {detail}")

    @property
    def retryable(self) -> bool:
        return self.status == 429 or 500 <= self.status < 600


class EventdSubscriptionMismatchError(EventdClientError):
    """A published event matched no configured durable subscription."""


@dataclass(frozen=True, slots=True)
class EventAcceptance:
    """Result returned after Event Daemon durably accepts a CloudEvent."""

    status: str
    event_seq: int
    matched_subscriptions: int


@dataclass(frozen=True, slots=True)
class Delivery:
    """One leased CloudEvent delivery."""

    delivery_id: str
    lease_token: str
    lease_until: int
    attempt: int
    event: CloudEvent

    @classmethod
    def parse(cls, raw: object) -> Delivery:
        if not isinstance(raw, dict):
            raise EventdClientError("delivery must be an object")
        delivery_id = raw.get("deliveryId")
        lease_token = raw.get("leaseToken")
        lease_until = raw.get("leaseUntil")
        attempt = raw.get("attempt")
        if not isinstance(delivery_id, str) or not delivery_id.strip():
            raise EventdClientError("delivery is missing deliveryId")
        if not isinstance(lease_token, str) or not lease_token.strip():
            raise EventdClientError("delivery is missing leaseToken")
        if not isinstance(lease_until, int) or isinstance(lease_until, bool) or lease_until <= 0:
            raise EventdClientError("delivery leaseUntil must be a positive integer")
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt <= 0:
            raise EventdClientError("delivery attempt must be a positive integer")
        try:
            event = CloudEvent.parse(raw.get("event"))
        except CloudEventError as e:
            raise EventdClientError(f"delivery contains an invalid CloudEvent: {e}") from e
        return cls(delivery_id.strip(), lease_token.strip(), lease_until, attempt, event)


@dataclass(slots=True)
class EventdClient:
    """Async-context-managed Event Daemon client shared by provider adapters."""

    daemon_endpoint: str
    api_token: str = ""
    _http: aiohttp.ClientSession | None = field(init=False, default=None, repr=False)
    _base: str = field(init=False, default="", repr=False)

    async def __aenter__(self) -> Self:
        if self._http is not None:
            raise RuntimeError("EventdClient is already open")
        connector, base = resolve_connector_and_endpoint(self.daemon_endpoint, path_prefix="")
        headers = {"Authorization": f"Bearer {self.api_token}"} if self.api_token else {}
        try:
            self._http = aiohttp.ClientSession(
                connector=connector,
                headers=headers,
                timeout=ClientTimeout(total=None),
            )
        except Exception:
            with anyio.CancelScope(shield=True):
                await connector.close()
            raise
        self._base = base
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        http = self._http
        self._http = None
        self._base = ""
        if http is not None:
            with anyio.CancelScope(shield=True):
                await http.close()

    async def publish(self, event: CloudEvent, *, require_match: bool = False) -> EventAcceptance:
        raw = await self._post_json("/v1/events", event.to_dict())
        status = raw.get("status")
        event_seq = raw.get("eventSeq")
        matched_subscriptions = raw.get("matchedSubscriptions")
        if status not in {"created", "duplicate"}:
            raise EventdClientError("publish response status must be created or duplicate")
        if not isinstance(event_seq, int) or isinstance(event_seq, bool) or event_seq <= 0:
            raise EventdClientError("publish response eventSeq must be a positive integer")
        if (
            not isinstance(matched_subscriptions, int)
            or isinstance(matched_subscriptions, bool)
            or matched_subscriptions < 0
        ):
            raise EventdClientError("publish response matchedSubscriptions must be a non-negative integer")
        acceptance = EventAcceptance(status.strip(), event_seq, matched_subscriptions)
        if require_match and matched_subscriptions == 0:
            raise EventdSubscriptionMismatchError(
                f"CloudEvent source={event.source!r} type={event.type!r} matched no Event Daemon subscription"
            )
        return acceptance

    async def get_subscription(self, subscription_id: str) -> Subscription:
        subscription_id = subscription_id.strip()
        if not subscription_id:
            raise ValueError("subscription_id must be non-empty")
        raw = await self._request_json(
            "GET",
            f"/internal/v1/subscriptions/{quote(subscription_id, safe='')}",
        )
        identifier = raw.get("id")
        filt = raw.get("filter")
        lease_seconds = raw.get("leaseSeconds")
        max_attempts = raw.get("maxAttempts")
        if not isinstance(identifier, str) or not identifier.strip():
            raise EventdClientError("subscription response id must be a non-empty string")
        if identifier.strip() != subscription_id:
            raise EventdClientError(
                f"subscription response id {identifier.strip()!r} does not match requested id {subscription_id!r}"
            )
        if not isinstance(filt, dict):
            raise EventdClientError("subscription response filter must be an object")
        source_prefix = filt.get("sourcePrefix")
        types = filt.get("types")
        if not isinstance(source_prefix, str):
            raise EventdClientError("subscription filter sourcePrefix must be a string")
        if not isinstance(types, list) or any(not isinstance(item, str) or not item.strip() for item in types):
            raise EventdClientError("subscription filter types must be a list of non-empty strings")
        if not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool) or lease_seconds <= 0:
            raise EventdClientError("subscription leaseSeconds must be a positive integer")
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts <= 0:
            raise EventdClientError("subscription maxAttempts must be a positive integer")
        return Subscription(
            id=identifier.strip(),
            source_prefix=source_prefix.strip(),
            types=tuple(item.strip() for item in cast(list[str], types)),
            lease_seconds=lease_seconds,
            max_attempts=max_attempts,
        )

    async def claim(
        self,
        *,
        subscription_id: str,
        instance_id: str,
        limit: int = 1,
        lease_seconds: int = 0,
        wait_seconds: int = 20,
    ) -> list[Delivery]:
        subscription_id = subscription_id.strip()
        instance_id = instance_id.strip()
        if not subscription_id or not instance_id:
            raise ValueError("subscription_id and instance_id must be non-empty")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool) or lease_seconds < 0:
            raise ValueError("lease_seconds must be a non-negative integer")
        if not isinstance(wait_seconds, int) or isinstance(wait_seconds, bool) or not 0 <= wait_seconds <= 30:
            raise ValueError("wait_seconds must be between 0 and 30")
        raw = await self._post_json(
            f"/internal/v1/subscriptions/{quote(subscription_id, safe='')}/claim",
            {
                "instanceId": instance_id,
                "limit": limit,
                "leaseSeconds": lease_seconds,
                "waitSeconds": wait_seconds,
            },
        )
        deliveries = raw.get("deliveries")
        if not isinstance(deliveries, list):
            raise EventdClientError("claim response deliveries must be a list")
        return [Delivery.parse(item) for item in deliveries]

    async def renew(self, delivery: Delivery, *, lease_seconds: int) -> None:
        if not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool) or lease_seconds <= 0:
            raise ValueError("lease_seconds must be a positive integer")
        await self._control(
            delivery,
            "renew",
            {"leaseToken": delivery.lease_token, "leaseSeconds": lease_seconds},
        )

    async def ack(self, delivery: Delivery) -> None:
        await self._control(delivery, "ack", {"leaseToken": delivery.lease_token})

    async def nack(self, delivery: Delivery, *, error: str, retry_seconds: int = 5) -> None:
        if not isinstance(retry_seconds, int) or isinstance(retry_seconds, bool) or retry_seconds < 0:
            raise ValueError("retry_seconds must be a non-negative integer")
        await self._control(
            delivery,
            "nack",
            {
                "leaseToken": delivery.lease_token,
                "error": error,
                "retrySeconds": retry_seconds,
            },
        )

    async def _control(self, delivery: Delivery, action: str, body: dict[str, object]) -> None:
        delivery_id = quote(delivery.delivery_id, safe="")
        await self._post_json(f"/internal/v1/deliveries/{delivery_id}/{action}", body)

    async def _post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return await self._request_json("POST", path, body)

    async def _request_json(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        http = self._http
        if http is None:
            raise RuntimeError("EventdClient must be used as an async context manager")
        async with http.request(method, self._base + path, json=body) as response:
            try:
                raw = await response.json()
            except Exception as e:
                if response.status >= 400:
                    raise EventdResponseError(path, response.status, f"invalid JSON response: {e}") from e
                raise EventdClientError(f"{path} returned invalid JSON: {e}") from e
            if not isinstance(raw, dict):
                if response.status >= 400:
                    raise EventdResponseError(path, response.status, "response must be an object")
                raise EventdClientError(f"{path} response must be an object")
            if response.status >= 400:
                raise EventdResponseError(path, response.status, str(raw.get("error") or "request failed"))
            return cast(dict[str, Any], raw)
