"""YAML configuration parsing for Event Daemon and its consumer."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, cast
from urllib.parse import urlsplit

import anyio
import yaml

from psi_agent._appdata import resolve_appdata_root
from psi_agent.eventd.schema import Hook, Subscription


def mapping(value: object, name: str) -> dict[str, Any]:
    """Return a defensive mapping copy for adapter and daemon config parsers."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return cast(dict[str, Any], value).copy()


def string_list(value: object, name: str) -> tuple[str, ...]:
    """Parse an optional list of non-empty strings."""
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{name} must be a list of non-empty strings")
    return tuple(item.strip() for item in cast(list[str], value))


def positive_int(value: object, default: int, name: str) -> int:
    """Parse an optional positive integer with a caller-provided default."""
    candidate = default if value is None else value
    if not isinstance(candidate, int) or isinstance(candidate, bool) or candidate <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return candidate


def non_negative_int(value: object, default: int, name: str) -> int:
    """Parse an optional non-negative integer with a caller-provided default."""
    candidate = default if value is None else value
    if not isinstance(candidate, int) or isinstance(candidate, bool) or candidate < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return candidate


def secret_from_env_ref(value: object, name: str, *, required: bool = False) -> str:
    """Resolve an ``env://NAME`` secret without accepting literal config secrets."""
    reference = str(value or "").strip()
    if not reference:
        if required:
            raise ValueError(f"{name} is required")
        return ""
    if not reference.startswith("env://") or not reference.removeprefix("env://"):
        raise ValueError(f"{name} must be an env:// reference")
    secret = os.environ.get(reference.removeprefix("env://"), "").strip()
    if required and not secret:
        raise ValueError(f"{name} environment variable is empty")
    return secret


def webhook_token_from_env_ref(value: object, name: str) -> str:
    """Resolve a Webhook token that is safe as one unescaped URL path segment."""
    token = secret_from_env_ref(value, name, required=True)
    if any(not (character.isascii() and (character.isalnum() or character in "-._~")) for character in token):
        raise ValueError(f"{name} must resolve to an RFC 3986 unreserved token")
    return token


@dataclass(frozen=True, slots=True)
class DaemonConfig:
    listen: str
    data_path: str
    api_token: str
    subscriptions: tuple[Subscription, ...]
    hooks: tuple[Hook, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ConsumerConfig:
    daemon_endpoint: str
    subscription_id: str
    session_socket: str
    instance_id: str
    renew_every_seconds: int
    lease_seconds: int
    wait_seconds: int
    api_token: str
    routing: dict[str, Any] = field(default_factory=dict)


async def read_yaml(path: str) -> dict[str, Any]:
    """Read one YAML document and require an object at its root."""
    content = await anyio.Path(path).read_text(encoding="utf-8")
    return mapping(yaml.safe_load(content), "config")


async def load_daemon_config(
    *,
    path: str,
    listen: str,
    data_path: str,
    appdata: str,
    api_token: str,
) -> DaemonConfig:
    raw = await read_yaml(path) if path.strip() else {}
    daemon = mapping(raw.get("daemon"), "daemon")
    appdata_root = await resolve_appdata_root(appdata)
    configured_path = str(daemon.get("dataPath") or data_path).strip()
    if not configured_path:
        configured_path = str(anyio.Path(appdata_root) / "eventd" / "events.sqlite3")
    configured_listen = str(daemon.get("listen") or listen).strip()
    if not configured_listen:
        raise ValueError("daemon.listen cannot be empty")
    if daemon.get("apiToken"):
        raise ValueError("daemon.apiToken cannot contain a secret; use apiTokenRef: env://NAME")
    token = (
        os.environ.get("PSI_EVENTD_TOKEN", "").strip()
        or secret_from_env_ref(daemon.get("apiTokenRef"), "daemon.apiTokenRef")
        or api_token.strip()
    )
    parsed_listen = urlsplit(configured_listen)
    if parsed_listen.scheme in {"http", "https"}:
        host = (parsed_listen.hostname or "").casefold()
        if host not in {"127.0.0.1", "::1", "localhost"} and not token:
            raise ValueError("a non-loopback eventd listener requires PSI_EVENTD_TOKEN")

    subscriptions: list[Subscription] = []
    subscription_ids: set[str] = set()
    subscription_rows = raw.get("subscriptions", [])
    if not isinstance(subscription_rows, list):
        raise ValueError("subscriptions must be a list")
    for index, item in enumerate(subscription_rows):
        row = mapping(item, f"subscriptions[{index}]")
        subscription_id = str(row.get("id") or "").strip()
        if not subscription_id:
            raise ValueError(f"subscriptions[{index}].id cannot be empty")
        if subscription_id in subscription_ids:
            raise ValueError(f"duplicate subscription id: {subscription_id!r}")
        subscription_ids.add(subscription_id)
        filt = mapping(row.get("filter"), f"subscriptions[{index}].filter")
        subscriptions.append(
            Subscription(
                id=subscription_id,
                source_prefix=str(filt.get("sourcePrefix") or "").strip(),
                types=string_list(filt.get("types"), f"subscriptions[{index}].filter.types"),
                lease_seconds=positive_int(row.get("leaseSeconds"), 60, "leaseSeconds"),
                max_attempts=positive_int(row.get("maxAttempts"), 10, "maxAttempts"),
            )
        )
    hooks: list[Hook] = []
    hook_ids: set[str] = set()
    listener_rows = raw.get("webhookListeners", [])
    if not isinstance(listener_rows, list):
        raise ValueError("webhookListeners must be a list")
    for index, item in enumerate(listener_rows):
        row = mapping(item, f"webhookListeners[{index}]")
        listener_id = str(row.get("id") or "").strip()
        if (
            not listener_id
            or not listener_id[0].islower()
            or not listener_id[0].isascii()
            or any(not (character.isascii() and (character.isalnum() or character == "_")) for character in listener_id)
        ):
            raise ValueError(f"webhookListeners[{index}].id must be a lowercase FusionFlow identity")
        if listener_id in subscription_ids or listener_id in hook_ids:
            raise ValueError(f"duplicate webhook listener id: {listener_id!r}")
        if row.get("token"):
            raise ValueError(f"webhookListeners[{index}].token cannot contain a secret; use tokenRef: env://NAME")
        id_from = mapping(row.get("idFrom"), f"webhookListeners[{index}].idFrom")
        id_header = str(id_from.get("header") or "").strip()
        id_pointer = str(id_from.get("pointer") or "").strip()
        if id_header and id_pointer:
            raise ValueError(f"webhookListeners[{index}].idFrom accepts either header or pointer")
        if id_pointer and not id_pointer.startswith("/"):
            raise ValueError(f"webhookListeners[{index}].idFrom.pointer must start with '/'")

        source = f"webhook://eventd/{listener_id}/"
        subscriptions.append(
            Subscription(
                id=listener_id,
                source_prefix=source,
                lease_seconds=positive_int(
                    row.get("leaseSeconds"),
                    60,
                    f"webhookListeners[{index}].leaseSeconds",
                ),
                max_attempts=positive_int(
                    row.get("maxAttempts"),
                    10,
                    f"webhookListeners[{index}].maxAttempts",
                ),
            )
        )
        hooks.append(
            Hook(
                id=listener_id,
                token=webhook_token_from_env_ref(
                    row.get("tokenRef"),
                    f"webhookListeners[{index}].tokenRef",
                ),
                source=source,
                type="external.event.received",
                id_header=id_header,
                id_pointer=id_pointer,
            )
        )
        subscription_ids.add(listener_id)
        hook_ids.add(listener_id)

    hook_rows = raw.get("hooks", [])
    if not isinstance(hook_rows, list):
        raise ValueError("hooks must be a list")
    for index, item in enumerate(hook_rows):
        row = mapping(item, f"hooks[{index}]")
        hook_id = str(row.get("id") or "").strip()
        if not hook_id or "/" in hook_id:
            raise ValueError(f"hooks[{index}].id must be non-empty and cannot contain '/'")
        if hook_id in hook_ids:
            raise ValueError(f"duplicate hook id: {hook_id!r}")
        hook_ids.add(hook_id)
        if row.get("token"):
            raise ValueError(f"hooks[{index}].token cannot contain a secret; use tokenRef: env://NAME")
        id_from = mapping(row.get("idFrom"), f"hooks[{index}].idFrom")
        id_header = str(id_from.get("header") or "").strip()
        id_pointer = str(id_from.get("pointer") or "").strip()
        if id_header and id_pointer:
            raise ValueError(f"hooks[{index}].idFrom accepts either header or pointer")
        if id_pointer and not id_pointer.startswith("/"):
            raise ValueError(f"hooks[{index}].idFrom.pointer must start with '/'")
        source = str(row.get("source") or f"webhook://{hook_id}").strip()
        event_type = str(row.get("type") or "external.event.received").strip()
        if not source or not event_type:
            raise ValueError(f"hooks[{index}] requires non-empty source and type")
        hooks.append(
            Hook(
                id=hook_id,
                token=secret_from_env_ref(row.get("tokenRef"), f"hooks[{index}].tokenRef", required=True),
                source=source,
                type=event_type,
                id_header=id_header,
                id_pointer=id_pointer,
            )
        )
    if listener_rows and hook_rows and not subscription_rows:
        raise ValueError("mixing webhookListeners with manual hooks requires explicit subscriptions")
    if hook_rows and not subscription_rows:
        subscriptions.insert(0, Subscription(id="default"))
    elif not subscriptions:
        subscriptions.append(Subscription(id="default"))
    return DaemonConfig(configured_listen, configured_path, token, tuple(subscriptions), tuple(hooks))


async def load_consumer_config(
    *,
    path: str,
    daemon_endpoint: str,
    subscription_id: str,
    session_socket: str,
    instance_id: str,
    renew_every_seconds: int,
    lease_seconds: int,
    wait_seconds: int,
    api_token: str,
) -> ConsumerConfig:
    raw = await read_yaml(path) if path.strip() else {}
    consumer = mapping(raw.get("consumer"), "consumer")
    endpoint = str(consumer.get("daemonEndpoint") or daemon_endpoint).strip()
    subscription = str(consumer.get("subscriptionId") or subscription_id).strip()
    session = str(consumer.get("sessionSocket") or session_socket).strip()
    if not endpoint or not subscription or not session:
        raise ValueError("consumer requires daemonEndpoint, subscriptionId, and sessionSocket")
    routing = mapping(consumer.get("routing"), "consumer.routing")
    if consumer.get("apiToken"):
        raise ValueError("consumer.apiToken cannot contain a secret; use apiTokenRef: env://NAME")
    token = (
        os.environ.get("PSI_EVENTD_TOKEN", "").strip()
        or secret_from_env_ref(consumer.get("apiTokenRef"), "consumer.apiTokenRef")
        or api_token.strip()
    )
    configured_renew = positive_int(consumer.get("renewEverySeconds"), renew_every_seconds, "renewEverySeconds")
    configured_lease = non_negative_int(consumer.get("leaseSeconds"), lease_seconds, "leaseSeconds")
    if configured_lease and configured_renew >= configured_lease:
        raise ValueError("consumer.renewEverySeconds must be less than consumer.leaseSeconds")
    configured_wait = non_negative_int(consumer.get("waitSeconds"), wait_seconds, "waitSeconds")
    if configured_wait > 30:
        raise ValueError("consumer.waitSeconds must be between 0 and 30")
    return ConsumerConfig(
        endpoint,
        subscription,
        session,
        str(consumer.get("instanceId") or instance_id).strip(),
        configured_renew,
        configured_lease,
        configured_wait,
        token,
        routing,
    )
