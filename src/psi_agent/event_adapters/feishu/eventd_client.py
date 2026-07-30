"""HTTP-only client for the generic Event Daemon contract."""

from __future__ import annotations

from collections.abc import Mapping
from types import TracebackType
from typing import Any, Self, cast

import aiohttp
from aiohttp import ClientTimeout

from psi_agent._sockets import resolve_connector_and_endpoint
from psi_agent.eventd.schema import CloudEvent


class EventdClientError(RuntimeError):
    """An Event Daemon request failed or returned an invalid response."""


class EventdClient:
    def __init__(self, endpoint: str, api_token: str) -> None:
        self.endpoint = endpoint
        self.api_token = api_token
        self._http: aiohttp.ClientSession | None = None
        self._base = ""

    async def __aenter__(self) -> Self:
        connector, self._base = resolve_connector_and_endpoint(self.endpoint, path_prefix="")
        headers = {"Authorization": f"Bearer {self.api_token}"} if self.api_token else {}
        self._http = aiohttp.ClientSession(
            connector=connector,
            headers=headers,
            timeout=ClientTimeout(total=None),
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._http is not None:
            await self._http.close()
            self._http = None

    async def publish(self, event: CloudEvent, *, timeout_seconds: float | None = None) -> str:
        data = await self._post_json(
            "/v1/events",
            event.to_dict(),
            request_timeout=ClientTimeout(total=timeout_seconds) if timeout_seconds is not None else None,
            expected_status=202,
        )
        status = data.get("status")
        if status not in {"created", "duplicate"}:
            raise EventdClientError(f"Event Daemon returned invalid persistence status: {status!r}")
        return cast(str, status)

    async def claim(
        self,
        subscription_id: str,
        *,
        instance_id: str,
        lease_seconds: int,
        wait_seconds: int,
    ) -> list[dict[str, Any]]:
        data = await self._post_json(
            f"/internal/v1/subscriptions/{subscription_id}/claim",
            {
                "instanceId": instance_id,
                "limit": 1,
                "leaseSeconds": lease_seconds,
                "waitSeconds": wait_seconds,
            },
        )
        deliveries = data.get("deliveries")
        if not isinstance(deliveries, list) or any(not isinstance(item, dict) for item in deliveries):
            raise EventdClientError("claim response deliveries must be a list of objects")
        return cast(list[dict[str, Any]], deliveries)

    async def control(
        self,
        delivery_id: str,
        action: str,
        body: Mapping[str, object],
    ) -> dict[str, Any]:
        return await self._post_json(f"/internal/v1/deliveries/{delivery_id}/{action}", body)

    async def _post_json(
        self,
        path: str,
        body: Mapping[str, object],
        *,
        request_timeout: ClientTimeout | None = None,
        expected_status: int = 200,
    ) -> dict[str, Any]:
        if self._http is None:
            raise RuntimeError("EventdClient must be used as an async context manager")
        async with self._http.post(self._base + path, json=body, timeout=request_timeout) as response:
            try:
                raw = await response.json()
            except Exception as e:
                raise EventdClientError(f"{path} returned invalid JSON: {e}") from e
            if not isinstance(raw, dict):
                raise EventdClientError(f"{path} response must be an object")
            if response.status != expected_status:
                raise EventdClientError(f"{path} HTTP {response.status}: {raw.get('error')}")
            return cast(dict[str, Any], raw)
