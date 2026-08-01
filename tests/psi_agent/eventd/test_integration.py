from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

import anyio
import pytest
from aiohttp import web

from psi_agent.eventd.consumer import EventConsumerWorker
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
async def test_consumer_claims_dispatches_and_acks(tmp_path: Path) -> None:
    acked = anyio.Event()

    class AckStore(EventStore):
        async def ack(self, delivery_id: str, lease_token: str) -> bool:
            result = await super().ack(delivery_id, lease_token)
            if result:
                acked.set()
            return result

    store = AckStore(str(tmp_path / "events.sqlite3"))
    subscription = Subscription(id="finance", types=("approval.status.changed",))
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
            "feishu://tenant/app/approval",
            "approval.status.changed",
            {"approval_code": "expense", "status": "APPROVED"},
        )
    )
    worker = EventConsumerWorker(
        daemon_endpoint=eventd_url,
        subscription_id="finance",
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

    assert received[0]["event"] == "feishu.approval.status.changed"
    assert received[0]["idempotency_key"] == "feishu://tenant/app/approval|event-1"
    assert received[0]["routing"]["delivery_id"].startswith("delivery_")
    assert received[0]["routing"]["event_id"] == "event-1"
