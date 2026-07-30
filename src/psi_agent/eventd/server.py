"""aiohttp service for durable event ingress and lease-based consumption."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Any

import anyio
from aiohttp import web
from loguru import logger

from psi_agent._sockets import create_site
from psi_agent.eventd.schema import CloudEvent, CloudEventError, EventConflictError, Subscription
from psi_agent.eventd.store import EventStore


@dataclass(slots=True)
class EventService:
    store: EventStore
    subscriptions: tuple[Subscription, ...]

    async def initialize(self) -> None:
        await self.store.initialize()
        for subscription in self.subscriptions:
            await self.store.upsert_subscription(subscription)

    async def accept(self, event: CloudEvent) -> tuple[str, int]:
        targets = [subscription.id for subscription in self.subscriptions if subscription.matches(event)]
        return await self.store.ingest(event, targets)


def build_eventd_app(service: EventService, *, api_token: str = "") -> web.Application:
    app = web.Application(client_max_size=4 * 1024 * 1024)

    async def authorize(request: web.Request) -> web.Response | None:
        if not api_token:
            return None
        supplied = request.headers.get("Authorization", "")
        if not hmac.compare_digest(supplied, f"Bearer {api_token}"):
            return web.json_response({"error": "unauthorized"}, status=401)
        return None

    async def livez(_request: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    async def readyz(_request: web.Request) -> web.Response:
        ready = await service.store.ready()
        return web.json_response({"ok": ready}, status=200 if ready else 503)

    async def health_ingress(_request: web.Request) -> web.Response:
        connections = await service.store.connection_states()
        unhealthy = sorted(
            connection_id
            for connection_id, state in connections.items()
            if state.get("websocket") in {"disconnected", "reconnecting"}
        )
        return web.json_response(
            {
                "ok": not unhealthy,
                "deliveries": await service.store.stats(),
                "connections": connections,
                "unhealthyConnections": unhealthy,
            },
            status=200 if not unhealthy else 503,
        )

    async def receive_event(request: web.Request) -> web.Response:
        denied = await authorize(request)
        if denied is not None:
            return denied
        try:
            event = CloudEvent.parse(await request.json())
            status, event_seq = await service.accept(event)
        except CloudEventError as e:
            return web.json_response({"error": str(e)}, status=400)
        except EventConflictError as e:
            logger.warning(f"CloudEvent conflict: {e}")
            return web.json_response({"error": str(e)}, status=409)
        except Exception as e:
            logger.error(f"Event persistence failed: {e!r}")
            return web.json_response({"error": "storage unavailable"}, status=503)
        return web.json_response({"status": status, "eventSeq": event_seq}, status=202)

    async def claim(request: web.Request) -> web.Response:
        denied = await authorize(request)
        if denied is not None:
            return denied
        subscription_id = request.match_info["subscription_id"]
        try:
            body = await request.json()
        except Exception as e:
            return web.json_response({"error": f"invalid JSON: {e}"}, status=400)
        if not isinstance(body, dict):
            return web.json_response({"error": "body must be an object"}, status=400)
        instance_id = str(body.get("instanceId") or "").strip()
        if not instance_id:
            return web.json_response({"error": "instanceId is required"}, status=400)
        limit = body.get("limit", 1)
        lease_seconds = body.get("leaseSeconds", 60)
        wait_seconds = body.get("waitSeconds", 0)
        if any(not isinstance(value, int) or isinstance(value, bool) for value in (limit, lease_seconds, wait_seconds)):
            return web.json_response({"error": "limit, leaseSeconds, and waitSeconds must be integers"}, status=400)
        deadline = anyio.current_time() + max(0, min(wait_seconds, 30))
        while True:
            deliveries = await service.store.claim(
                subscription_id=subscription_id,
                instance_id=instance_id,
                limit=max(1, min(limit, 100)),
                lease_seconds=max(1, lease_seconds),
            )
            if deliveries or anyio.current_time() >= deadline:
                return web.json_response({"deliveries": deliveries})
            await anyio.sleep(0.25)

    async def control(request: web.Request) -> web.Response:
        denied = await authorize(request)
        if denied is not None:
            return denied
        delivery_id = request.match_info["delivery_id"]
        action = request.match_info["action"]
        try:
            body = await request.json()
        except Exception as e:
            return web.json_response({"error": f"invalid JSON: {e}"}, status=400)
        if not isinstance(body, dict):
            return web.json_response({"error": "body must be an object"}, status=400)
        token = str(body.get("leaseToken") or "").strip()
        if not token:
            return web.json_response({"error": "leaseToken is required"}, status=400)
        result: Any
        if action == "renew":
            seconds = body.get("leaseSeconds", 60)
            if not isinstance(seconds, int) or isinstance(seconds, bool) or seconds <= 0:
                return web.json_response({"error": "leaseSeconds must be a positive integer"}, status=400)
            result = await service.store.renew(delivery_id, token, seconds)
        elif action == "ack":
            result = await service.store.ack(delivery_id, token)
        else:
            retry_seconds = body.get("retrySeconds", 5)
            if not isinstance(retry_seconds, int) or isinstance(retry_seconds, bool) or retry_seconds < 0:
                return web.json_response({"error": "retrySeconds must be a non-negative integer"}, status=400)
            result = await service.store.nack(
                delivery_id, token, str(body.get("error") or "consumer rejected delivery"), retry_seconds
            )
        if not result:
            return web.json_response({"error": "stale lease"}, status=409)
        return web.json_response({"ok": True, "result": result})

    async def unsupported_webhook(request: web.Request) -> web.Response:
        denied = await authorize(request)
        if denied is not None:
            return denied
        return web.json_response(
            {"error": f"webhook adapter is not configured for {request.match_info['provider']!r}"}, status=501
        )

    app.router.add_get("/livez", livez)
    app.router.add_get("/readyz", readyz)
    app.router.add_get("/health/ingress", health_ingress)
    app.router.add_post("/v1/events", receive_event)
    app.router.add_post("/v1/webhooks/{provider}/{connection_id}", unsupported_webhook)
    app.router.add_post("/internal/v1/subscriptions/{subscription_id}/claim", claim)
    app.router.add_post("/internal/v1/deliveries/{delivery_id}/{action:renew|ack|nack}", control)
    return app


async def serve_eventd(service: EventService, *, listen: str, api_token: str = "") -> None:
    app = build_eventd_app(service, api_token=api_token)
    runner = web.AppRunner(app)
    try:
        await runner.setup()
        site = create_site(runner, listen)
        await site.start()
        logger.info(f"Event Daemon listening on {listen}")
        await anyio.sleep_forever()
    finally:
        with anyio.CancelScope(shield=True):
            await runner.cleanup()
