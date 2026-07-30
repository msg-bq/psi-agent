from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from psi_agent.event_adapters.feishu.sdk import (
    FeishuApprovalApi,
    json_value,
    register_approval_processor,
)


def test_register_approval_processor_isolated_compatibility_layer() -> None:
    processors: dict[str, object] = {}
    channel = SimpleNamespace(dispatcher=SimpleNamespace(_processorMap=processors))

    register_approval_processor(channel, lambda _event: None)

    assert set(processors) == {"p1.approval_instance", "p2.approval_instance"}


def test_register_approval_processor_fails_loudly_for_incompatible_sdk() -> None:
    with pytest.raises(RuntimeError, match=r"dispatcher\._processorMap"):
        register_approval_processor(SimpleNamespace(dispatcher=SimpleNamespace()), lambda _event: None)


def test_sdk_models_are_recursively_converted_to_finite_json() -> None:
    model = SimpleNamespace(event=SimpleNamespace(instance_code="instance-1", values=(1, float("nan"))))

    assert json_value(model) == {
        "event": {
            "instance_code": "instance-1",
            "values": [1, "nan"],
        }
    }


@pytest.mark.anyio
async def test_detail_response_decodes_nested_json() -> None:
    body = {
        "code": 0,
        "data": {
            "form": '[{"id":"amount","value":100}]',
            "task_list": "[]",
            "timeline": "[]",
        },
    }
    response = SimpleNamespace(raw=SimpleNamespace(content=json.dumps(body).encode()))
    channel = SimpleNamespace(client=SimpleNamespace(arequest=AsyncMock(return_value=response)))

    detail = await FeishuApprovalApi(channel).fetch_detail("instance-1")

    assert detail["form"] == [{"id": "amount", "value": 100}]
