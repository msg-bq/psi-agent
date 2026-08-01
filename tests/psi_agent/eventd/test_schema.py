from __future__ import annotations

import pytest

from psi_agent.eventd.schema import CloudEvent, CloudEventError, Subscription, cloud_event_to_session_envelope


def test_cloud_event_requires_exact_five_fields() -> None:
    raw = {
        "specversion": "1.0",
        "id": "event-1",
        "source": "feishu://tenant/app/approval",
        "type": "approval.status.changed",
        "data": {"approval_code": "expense"},
    }
    event = CloudEvent.parse(raw)
    assert event.to_dict() == raw
    with pytest.raises(CloudEventError, match="exactly five"):
        CloudEvent.parse({**raw, "time": "2026-01-01"})


def test_subscription_and_session_translation() -> None:
    event = CloudEvent(
        "1.0",
        "event-1",
        "feishu://tenant/app/approval",
        "approval.status.changed",
        {
            "approval_code": "expense",
            "instance_code": "instance-1",
            "instance_operate_time": "1000",
        },
    )
    subscription = Subscription(
        id="finance",
        source_prefix="feishu://tenant/",
        types=("approval.status.changed",),
        approval_codes=("expense",),
    )
    assert subscription.matches(event)
    envelope = cloud_event_to_session_envelope(event, routing={"session_id": "finance-agent"})
    assert envelope["event"] == "feishu.approval.status.changed"
    assert envelope["raw_event"] == "approval_instance"
    assert envelope["occurred_at"] == "1000"
    assert envelope["routing"] == {"session_id": "finance-agent"}
