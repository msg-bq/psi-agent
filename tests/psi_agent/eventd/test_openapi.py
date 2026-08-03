from __future__ import annotations

from psi_agent.eventd.openapi import eventd_openapi


def test_openapi_describes_strict_ingress_and_adapter_runtime() -> None:
    document = eventd_openapi()

    assert document["openapi"] == "3.1.0"
    assert "/openapi.json" in document["paths"]
    assert "/v1/events" in document["paths"]
    assert "/internal/v1/subscriptions/{subscription_id}" in document["paths"]
    assert "/internal/v1/subscriptions/{subscription_id}/claim" in document["paths"]
    cloud_event = document["components"]["schemas"]["CloudEvent"]
    assert cloud_event["required"] == ["specversion", "id", "source", "type", "data"]
    assert cloud_event["additionalProperties"] is False
    assert cloud_event["properties"]["data"] == {}


def test_openapi_returns_defensive_copy() -> None:
    first = eventd_openapi()
    first["info"]["title"] = "mutated"

    assert eventd_openapi()["info"]["title"] == "psi-agent Event Daemon API"
