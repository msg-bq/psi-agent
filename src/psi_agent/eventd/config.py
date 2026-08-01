"""YAML configuration parsing for Event Daemon and its consumer."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, cast
from urllib.parse import urlsplit

import anyio
import yaml

from psi_agent._appdata import resolve_appdata_root
from psi_agent.eventd.schema import Subscription


def _mapping(value: object, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return cast(dict[str, Any], value)


def _string_list(value: object, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{name} must be a list of non-empty strings")
    values = cast(list[str], value)
    return tuple(item.strip() for item in values)


def _positive_int(value: object, default: int, name: str) -> int:
    if value is None:
        return default
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _secret_from_env_ref(value: object, name: str) -> str:
    reference = str(value or "").strip()
    if not reference:
        return ""
    if not reference.startswith("env://") or not reference.removeprefix("env://"):
        raise ValueError(f"{name} must be an env:// reference")
    return os.environ.get(reference.removeprefix("env://"), "").strip()


@dataclass(frozen=True, slots=True)
class FeishuConnection:
    id: str
    transport: str
    tenant_id: str
    app_id: str
    app_secret: str
    approval_codes: tuple[str, ...]
    reconciliation_enabled: bool = False
    reconciliation_interval_seconds: int = 900
    reconciliation_overlap_seconds: int = 3600


@dataclass(frozen=True, slots=True)
class DaemonConfig:
    listen: str
    data_path: str
    api_token: str
    subscriptions: tuple[Subscription, ...]
    connections: tuple[FeishuConnection, ...] = field(default_factory=tuple)


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


async def _read_yaml(path: str) -> dict[str, Any]:
    content = await anyio.Path(path).read_text(encoding="utf-8")
    raw = yaml.safe_load(content)
    return _mapping(raw, "config")


async def load_daemon_config(
    *,
    path: str,
    listen: str,
    data_path: str,
    appdata: str,
    api_token: str,
) -> DaemonConfig:
    raw = await _read_yaml(path) if path.strip() else {}
    daemon = _mapping(raw.get("daemon"), "daemon")
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
        or _secret_from_env_ref(daemon.get("apiTokenRef"), "daemon.apiTokenRef")
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
        row = _mapping(item, f"subscriptions[{index}]")
        subscription_id = str(row.get("id") or "").strip()
        if not subscription_id:
            raise ValueError(f"subscriptions[{index}].id cannot be empty")
        if subscription_id in subscription_ids:
            raise ValueError(f"duplicate subscription id: {subscription_id!r}")
        subscription_ids.add(subscription_id)
        filt = _mapping(row.get("filter"), f"subscriptions[{index}].filter")
        data_filter = _mapping(filt.get("data"), f"subscriptions[{index}].filter.data")
        subscriptions.append(
            Subscription(
                id=subscription_id,
                source_prefix=str(filt.get("sourcePrefix") or "").strip(),
                types=_string_list(filt.get("types"), f"subscriptions[{index}].filter.types"),
                approval_codes=_string_list(
                    data_filter.get("approvalCodes"), f"subscriptions[{index}].filter.data.approvalCodes"
                ),
                lease_seconds=_positive_int(row.get("leaseSeconds"), 60, "leaseSeconds"),
                max_attempts=_positive_int(row.get("maxAttempts"), 10, "maxAttempts"),
                dead_letter_after_seconds=_positive_int(
                    row.get("deadLetterAfterSeconds"), 604800, "deadLetterAfterSeconds"
                ),
            )
        )
    if not subscriptions:
        subscriptions.append(Subscription(id="haitun-events"))

    connections: list[FeishuConnection] = []
    connection_ids: set[str] = set()
    connection_rows = raw.get("connections", [])
    if not isinstance(connection_rows, list):
        raise ValueError("connections must be a list")
    for index, item in enumerate(connection_rows):
        row = _mapping(item, f"connections[{index}]")
        provider = str(row.get("provider") or "").strip().casefold()
        if provider != "feishu":
            raise ValueError(f"connections[{index}].provider must be 'feishu' in this release")
        transport = str(row.get("transport") or "websocket").strip().casefold()
        if transport not in {"websocket", "webhook"}:
            raise ValueError(f"connections[{index}].transport must be websocket or webhook")
        app_id = str(row.get("appId") or os.environ.get("PSI_FEISHU_APP_ID", "")).strip()
        secret_ref = str(row.get("appSecretRef") or "").strip()
        if secret_ref and not secret_ref.startswith("env://"):
            raise ValueError("only env:// secret references are supported")
        secret_env = secret_ref.removeprefix("env://") if secret_ref else "PSI_FEISHU_APP_SECRET"
        app_secret = os.environ.get(secret_env, "").strip()
        if not app_id or not app_secret:
            raise ValueError(f"connections[{index}] requires appId and an environment-backed appSecretRef")
        reconciliation = _mapping(row.get("reconciliation"), f"connections[{index}].reconciliation")
        connection_id = str(row.get("id") or f"feishu-{index}").strip()
        if not connection_id:
            raise ValueError(f"connections[{index}].id cannot be empty")
        if connection_id in connection_ids:
            raise ValueError(f"duplicate connection id: {connection_id!r}")
        connection_ids.add(connection_id)
        connections.append(
            FeishuConnection(
                id=connection_id,
                transport=transport,
                tenant_id=str(row.get("tenantId") or "default").strip(),
                app_id=app_id,
                app_secret=app_secret,
                approval_codes=_string_list(row.get("approvalCodes"), f"connections[{index}].approvalCodes"),
                reconciliation_enabled=bool(reconciliation.get("enabled", False)),
                reconciliation_interval_seconds=_positive_int(
                    reconciliation.get("intervalSeconds"), 900, "reconciliation.intervalSeconds"
                ),
                reconciliation_overlap_seconds=_positive_int(
                    reconciliation.get("overlapSeconds"), 3600, "reconciliation.overlapSeconds"
                ),
            )
        )
    return DaemonConfig(configured_listen, configured_path, token, tuple(subscriptions), tuple(connections))


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
    raw = await _read_yaml(path) if path.strip() else {}
    consumer = _mapping(raw.get("consumer"), "consumer")
    endpoint = str(consumer.get("daemonEndpoint") or daemon_endpoint).strip()
    subscription = str(consumer.get("subscriptionId") or subscription_id).strip()
    session = str(consumer.get("sessionSocket") or session_socket).strip()
    if not endpoint or not subscription or not session:
        raise ValueError("consumer requires daemonEndpoint, subscriptionId, and sessionSocket")
    routing = _mapping(consumer.get("routing"), "consumer.routing")
    if consumer.get("apiToken"):
        raise ValueError("consumer.apiToken cannot contain a secret; use apiTokenRef: env://NAME")
    token = (
        os.environ.get("PSI_EVENTD_TOKEN", "").strip()
        or _secret_from_env_ref(consumer.get("apiTokenRef"), "consumer.apiTokenRef")
        or api_token.strip()
    )
    configured_renew = _positive_int(consumer.get("renewEverySeconds"), renew_every_seconds, "renewEverySeconds")
    configured_lease = _positive_int(consumer.get("leaseSeconds"), lease_seconds, "leaseSeconds")
    if configured_renew >= configured_lease:
        raise ValueError("consumer.renewEverySeconds must be less than consumer.leaseSeconds")
    return ConsumerConfig(
        endpoint,
        subscription,
        session,
        str(consumer.get("instanceId") or instance_id).strip(),
        configured_renew,
        configured_lease,
        _positive_int(consumer.get("waitSeconds"), wait_seconds, "waitSeconds"),
        token,
        routing,
    )
