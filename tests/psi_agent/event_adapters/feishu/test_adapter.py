from __future__ import annotations

import socket
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from aiohttp import web

from psi_agent.event_adapters.feishu.adapter import FeishuApprovalAdapterService
from psi_agent.event_adapters.feishu.config import FeishuApprovalSettings
from psi_agent.event_adapters.feishu.eventd_client import EventdClient
from psi_agent.event_adapters.feishu.sdk import FeishuApprovalApi
from psi_agent.eventd.schema import CloudEvent, Subscription
from psi_agent.eventd.server import EventService, build_eventd_app
from psi_agent.eventd.store import EventStore


def _settings() -> FeishuApprovalSettings:
    return FeishuApprovalSettings(
        eventd_endpoint="http://127.0.0.1:1",
        raw_subscription_id="feishu-approval-normalizer",
        eventd_token="secret",
        tenant_id="tenant-a",
        app_id="cli_adapter",
        app_secret="app-secret",
        approval_codes=("expense",),
        wait_seconds=1,
    )


async def _start(app: web.Application) -> tuple[web.AppRunner, str]:
    runner = web.AppRunner(app)
    await runner.setup()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    await web.SockSite(runner, sock).start()
    return runner, f"http://127.0.0.1:{port}"


def test_normalized_event_has_live_reconciliation_stable_identity() -> None:
    service = FeishuApprovalAdapterService(_settings())
    payload = {
        "approval_code": "expense",
        "instance_code": "instance-1",
        "status": "APPROVED",
        "instance_operate_time": "1000",
    }
    detail = {
        "approval_name": "Expense",
        "user_id": "ou_user",
        "form": [
            {
                "id": "invoice",
                "name": "Invoice",
                "type": "attachmentV2",
                "value": ["https://example.test/invoice"],
            }
        ],
    }

    live = service._normalized_event(payload, detail)
    reconciled = service._normalized_event(payload, detail)

    assert live.id == reconciled.id
    assert live.source == "feishu://tenant-a/cli_adapter/approval"
    assert live.type == "approval.status.changed"
    assert live.data["applicant"] == "ou_user"
    assert live.data["attachments"][0]["name"] == "Invoice"


@pytest.mark.anyio
async def test_raw_event_is_persisted_then_enriched_through_generic_eventd(tmp_path: Path) -> None:
    settings = _settings()
    subscriptions = (
        Subscription(
            id=settings.raw_subscription_id,
            source_prefix=f"{settings.source}/raw",
            types=("feishu.approval.instance.received",),
        ),
        Subscription(id="business", types=("approval.status.changed",)),
    )
    store = EventStore(str(tmp_path / "events.sqlite3"))
    event_service = EventService(store, subscriptions)
    await event_service.initialize()
    runner, base = await _start(build_eventd_app(event_service, api_token="secret"))

    detail = {
        "approval_name": "Expense",
        "user_id": "ou_user",
        "form": [],
        "task_list": [],
        "timeline": [],
    }

    class FakeApprovalApi:
        async def fetch_detail(self, instance_code: str) -> dict[str, Any]:
            assert instance_code == "instance-1"
            return detail

    adapter = FeishuApprovalAdapterService(settings)
    try:
        async with EventdClient(base, "secret") as client:
            adapter._eventd = client
            adapter._api = cast(FeishuApprovalApi, FakeApprovalApi())
            sdk_event = SimpleNamespace(
                header=SimpleNamespace(event_id="provider-event-1"),
                event={
                    "approval_code": "expense",
                    "instance_code": "instance-1",
                    "status": "APPROVED",
                    "instance_operate_time": "1000",
                },
            )
            raw = await adapter.persist_raw(sdk_event)
            duplicate = await adapter.persist_raw(sdk_event)
            assert raw.id == duplicate.id == "provider-event-1"

            deliveries = await client.claim(
                settings.raw_subscription_id,
                instance_id="test-normalizer",
                lease_seconds=60,
                wait_seconds=1,
            )
            await adapter._process_delivery(deliveries[0])

            business = await client.claim(
                "business",
                instance_id="test-consumer",
                lease_seconds=60,
                wait_seconds=1,
            )
            normalized = business[0]["event"]
            assert normalized["type"] == "approval.status.changed"
            assert normalized["data"]["instance_code"] == "instance-1"
            assert (
                await client.claim(
                    settings.raw_subscription_id,
                    instance_id="test-normalizer",
                    lease_seconds=60,
                    wait_seconds=1,
                )
                == []
            )
    finally:
        adapter._api = None
        adapter._eventd = None
        await runner.cleanup()


@pytest.mark.anyio
async def test_detail_failure_nacks_raw_delivery_for_retry() -> None:
    controls: list[tuple[str, str, dict[str, object]]] = []

    class FakeEventd:
        async def control(
            self,
            delivery_id: str,
            action: str,
            body: dict[str, object],
        ) -> dict[str, Any]:
            controls.append((delivery_id, action, body))
            return {"ok": True}

    class FailingApprovalApi:
        async def fetch_detail(self, _instance_code: str) -> dict[str, Any]:
            raise RuntimeError("temporary Feishu API failure")

    settings = _settings()
    adapter = FeishuApprovalAdapterService(settings)
    adapter._eventd = cast(EventdClient, FakeEventd())
    adapter._api = cast(FeishuApprovalApi, FailingApprovalApi())
    raw_event = CloudEvent(
        "1.0",
        "raw-1",
        f"{settings.source}/raw",
        "feishu.approval.instance.received",
        {
            "header": {},
            "event": {
                "approval_code": "expense",
                "instance_code": "instance-1",
                "status": "APPROVED",
            },
        },
    )

    await adapter._process_delivery(
        {
            "deliveryId": "delivery-1",
            "leaseToken": "lease-1",
            "event": raw_event.to_dict(),
        }
    )

    assert controls == [
        (
            "delivery-1",
            "nack",
            {
                "leaseToken": "lease-1",
                "error": "temporary Feishu API failure",
                "retrySeconds": 5,
            },
        )
    ]


@pytest.mark.anyio
async def test_unconfigured_approval_is_acked_without_detail_lookup() -> None:
    controls: list[tuple[str, str]] = []

    class FakeEventd:
        async def control(
            self,
            delivery_id: str,
            action: str,
            _body: dict[str, object],
        ) -> dict[str, Any]:
            controls.append((delivery_id, action))
            return {"ok": True}

    settings = _settings()
    adapter = FeishuApprovalAdapterService(settings)
    adapter._eventd = cast(EventdClient, FakeEventd())
    raw_event = CloudEvent(
        "1.0",
        "raw-ignored",
        f"{settings.source}/raw",
        "feishu.approval.instance.received",
        {
            "header": {},
            "event": {
                "approval_code": "not-configured",
                "instance_code": "instance-2",
                "status": "APPROVED",
            },
        },
    )

    await adapter._process_delivery(
        {
            "deliveryId": "delivery-ignored",
            "leaseToken": "lease-ignored",
            "event": raw_event.to_dict(),
        }
    )

    assert controls == [("delivery-ignored", "ack")]
