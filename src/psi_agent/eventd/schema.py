"""Protocol types for the generic durable Event Daemon."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, cast


class CloudEventError(ValueError):
    """A strict five-field CloudEvent failed validation."""


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

    def identity_key(self) -> str:
        """Return a bounded, collision-resistant key for the ``(source, id)`` identity."""
        identity = json.dumps(
            [self.source, self.id],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return f"cloudevent/sha256:{hashlib.sha256(identity.encode()).hexdigest()}"


@dataclass(frozen=True, slots=True)
class Subscription:
    """A durable delivery target and its coarse event filter."""

    id: str
    source_prefix: str = ""
    types: tuple[str, ...] = ()
    lease_seconds: int = 60
    max_attempts: int = 10

    def matches(self, event: CloudEvent) -> bool:
        if self.source_prefix and not event.source.startswith(self.source_prefix):
            return False
        return not self.types or event.type in self.types

    def filter_dict(self) -> dict[str, Any]:
        return {"sourcePrefix": self.source_prefix, "types": list(self.types)}


@dataclass(frozen=True, slots=True)
class Hook:
    """Configuration for one URL-only JSON webhook."""

    id: str
    token: str
    source: str
    type: str
    id_header: str = ""
    id_pointer: str = ""

    def event_id(self, payload: object, headers: dict[str, str]) -> str:
        if self.id_header:
            value = headers.get(self.id_header.casefold(), "").strip()
            if value:
                return value
        if self.id_pointer:
            value: object = payload
            for raw_part in self.id_pointer.removeprefix("/").split("/"):
                part = raw_part.replace("~1", "/").replace("~0", "~")
                if isinstance(value, dict) and part in value:
                    value = cast(dict[str, object], value)[part]
                elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
                    value = value[int(part)]
                else:
                    value = ""
                    break
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, int) and not isinstance(value, bool):
                return str(value)
        return ""


def cloud_event_to_session_envelope(event: CloudEvent, *, routing: dict[str, Any] | None = None) -> dict[str, object]:
    """Translate a CloudEvent into the Session shape without losing its data type."""
    payload = cast(dict[str, Any], event.data).copy() if isinstance(event.data, dict) else {"value": event.data}
    return {
        "schema_version": 1,
        "source": "eventd",
        "event": event.type,
        "payload": payload,
        "occurred_at": "",
        "idempotency_key": event.identity_key(),
        "routing": dict(routing or {}),
        "raw_event": "",
        "raw_payload": {},
        "cloud_event": event.to_dict(),
    }
