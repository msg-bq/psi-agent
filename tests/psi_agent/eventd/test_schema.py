from __future__ import annotations

import pytest

from psi_agent.eventd.schema import CloudEvent, CloudEventError, Hook, Subscription, cloud_event_to_session_envelope


def test_cloud_event_requires_exact_five_fields() -> None:
    raw = {
        "specversion": "1.0",
        "id": "event-1",
        "source": "shop://orders",
        "type": "order.paid",
        "data": {"order_id": "1001"},
    }
    event = CloudEvent.parse(raw)
    assert event.to_dict() == raw
    with pytest.raises(CloudEventError, match="exactly five"):
        CloudEvent.parse({**raw, "time": "2026-01-01"})


def test_subscription_and_session_translation_are_provider_neutral() -> None:
    event = CloudEvent("1.0", "event-1", "shop://orders", "order.paid", {"order_id": "1001"})
    subscription = Subscription(id="orders", source_prefix="shop://", types=("order.paid",))
    assert subscription.matches(event)
    envelope = cloud_event_to_session_envelope(event, routing={"session_id": "order-agent"})
    assert envelope["source"] == "eventd"
    assert envelope["event"] == "order.paid"
    assert envelope["payload"] == {"order_id": "1001"}
    assert envelope["raw_event"] == ""
    assert envelope["routing"] == {"session_id": "order-agent"}
    assert envelope["cloud_event"] == event.to_dict()
    assert envelope["idempotency_key"] == event.identity_key()


def test_non_object_data_is_wrapped_for_session() -> None:
    event = CloudEvent("1.0", "event-1", "sensor://temperature", "temperature.read", 21.5)
    envelope = cloud_event_to_session_envelope(event)
    assert envelope["payload"] == {"value": 21.5}
    assert envelope["cloud_event"] == event.to_dict()


def test_identity_key_cannot_collide_on_delimiter_placement() -> None:
    first = CloudEvent("1.0", "c", "a|b", "test.event", {})
    second = CloudEvent("1.0", "b|c", "a", "test.event", {})

    assert first.identity_key() != second.identity_key()


def test_hook_identity_from_case_insensitive_header_or_json_pointer() -> None:
    header_hook = Hook("orders", "secret", "webhook://orders", "order.received", id_header="X-Event-Id")
    assert header_hook.event_id({}, {"x-event-id": "event-1"}) == "event-1"
    pointer_hook = Hook("orders", "secret", "webhook://orders", "order.received", id_pointer="/event/id")
    assert pointer_hook.event_id({"event": {"id": 42}}, {}) == "42"
    assert pointer_hook.event_id({"event": {}}, {}) == ""
