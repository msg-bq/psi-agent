"""CloudEvent and durable-delivery protocol types for Event Daemon."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, cast


class CloudEventError(ValueError):
    """A five-field CloudEvent failed validation."""


class EventConflictError(ValueError):
    """The same ``(source, id)`` arrived with different content."""


@dataclass(frozen=True, slots=True)
class CloudEvent:
    """The strict five-field CloudEvents 1.0 profile used by Event Daemon."""

    specversion: str
    id: str
    source: str
    type: str
    data: Any

    @classmethod
    def parse(cls, raw: object) -> CloudEvent:
        if not isinstance(raw, dict):
            raise CloudEventError("CloudEvent must be a JSON object")
        expected = {"specversion", "id", "source", "type", "data"}
        actual = set(raw)
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise CloudEventError(f"CloudEvent must contain exactly five fields; missing={missing}, extra={extra}")
        if raw.get("specversion") != "1.0":
            raise CloudEventError("specversion must be '1.0'")
        values: dict[str, str] = {}
        for name in ("id", "source", "type"):
            value = raw.get(name)
            if not isinstance(value, str) or not value.strip():
                raise CloudEventError(f"{name} must be a non-empty string")
            values[name] = value.strip()
        data = raw.get("data")
        try:
            json.dumps(data, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as e:
            raise CloudEventError(f"data must be finite JSON: {e}") from e
        return cls("1.0", values["id"], values["source"], values["type"], data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "specversion": self.specversion,
            "id": self.id,
            "source": self.source,
            "type": self.type,
            "data": self.data,
        }

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

    def content_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class Subscription:
    """A durable delivery target and its coarse event filter."""

    id: str
    source_prefix: str = ""
    types: tuple[str, ...] = ()
    approval_codes: tuple[str, ...] = ()
    lease_seconds: int = 60
    max_attempts: int = 10
    dead_letter_after_seconds: int = 604800

    def matches(self, event: CloudEvent) -> bool:
        if self.source_prefix and not event.source.startswith(self.source_prefix):
            return False
        if self.types and event.type not in self.types:
            return False
        if self.approval_codes:
            data = event.data
            if not isinstance(data, dict) or data.get("approval_code") not in self.approval_codes:
                return False
        return True

    def filter_dict(self) -> dict[str, Any]:
        return {
            "sourcePrefix": self.source_prefix,
            "types": list(self.types),
            "data": {"approvalCodes": list(self.approval_codes)},
        }


def cloud_event_to_session_envelope(event: CloudEvent, *, routing: dict[str, Any] | None = None) -> dict[str, object]:
    """Translate the durable CloudEvent into the existing Session event shape."""
    provider = event.source.split(":", 1)[0].strip().casefold()
    session_event = event.type if event.type.startswith(f"{provider}.") else f"{provider}.{event.type}"
    payload = cast(dict[str, Any], event.data).copy() if isinstance(event.data, dict) else {"value": event.data}
    occurred_at = str(payload.get("instance_operate_time") or payload.get("occurred_at") or "")
    raw_event = "approval_instance" if session_event == "feishu.approval.status.changed" else ""
    return {
        "schema_version": 1,
        "source": provider,
        "event": session_event,
        "payload": payload,
        "occurred_at": occurred_at,
        "idempotency_key": f"{event.source}|{event.id}",
        "routing": dict(routing or {}),
        "raw_event": raw_event,
        "raw_payload": {},
    }
