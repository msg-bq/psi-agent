from __future__ import annotations

from typing import Any, cast

import pytest

from psi_agent.eventd.adapters import feishu
from psi_agent.eventd.adapters.feishu import FeishuApprovalIngress, _attachments
from psi_agent.eventd.config import FeishuConnection
from psi_agent.eventd.server import EventService


def test_attachment_metadata_and_deterministic_approval_event() -> None:
    form = [
        {"id": "file", "name": "发票", "type": "attachmentV2", "value": ["https://example/file"]},
        {"id": "doc", "name": "说明", "type": "document", "value": "doc-token"},
    ]
    assert [item["kind"] for item in _attachments(form)] == ["url", "drive"]
    connection = FeishuConnection(
        id="finance",
        transport="websocket",
        tenant_id="tenant",
        app_id="app",
        app_secret="secret",
        approval_codes=("expense",),
    )
    ingress = FeishuApprovalIngress(cast(EventService, None), connection, cast(Any, None))
    payload = {
        "approval_code": "expense",
        "instance_code": "instance-1",
        "status": "APPROVED",
        "instance_operate_time": "1000",
    }
    detail = {"approval_name": "报销", "user_id": "ou_user", "form": form}
    first = ingress._cloud_event(payload, detail, "provider-live-id")
    second = ingress._cloud_event(payload, detail, "")
    assert first.id == second.id
    assert first.source == "feishu://tenant/app/approval"
    assert first.data["attachments"][0]["name"] == "发票"


@pytest.mark.anyio
async def test_connection_supervisor_records_failure_and_backs_off(monkeypatch: pytest.MonkeyPatch) -> None:
    states: dict[tuple[str, str], str] = {}
    delays: list[float] = []

    class StopRetryError(Exception):
        pass

    class FakeStore:
        async def set_connection_state(self, connection_id: str, key: str, value: str) -> None:
            states[(connection_id, key)] = value

    async def fail_connection(_service: object, _connection: object) -> None:
        raise RuntimeError("connection failed")

    async def stop_after_delay(delay: float) -> None:
        delays.append(delay)
        raise StopRetryError

    monkeypatch.setattr(feishu, "_run_connection_once", fail_connection)
    monkeypatch.setattr(feishu.random, "uniform", lambda _low, _high: 1.0)
    monkeypatch.setattr(feishu.anyio, "sleep", stop_after_delay)
    connection = FeishuConnection(
        id="finance",
        transport="websocket",
        tenant_id="tenant",
        app_id="app",
        app_secret="secret",
        approval_codes=("expense",),
    )
    service = cast(EventService, type("Service", (), {"store": FakeStore()})())
    with pytest.raises(StopRetryError):
        await feishu._supervise_connection(service, connection)
    assert states[("finance", "websocket")] == "reconnecting"
    assert states[("finance", "reconnect_count")] == "1"
    assert "connection failed" in states[("finance", "last_error")]
    assert delays == [1.0]
