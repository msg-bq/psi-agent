"""Configuration for the standalone Feishu approval event adapter."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, cast

import anyio
import yaml


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return cast(dict[str, Any], value)


def _positive_int(value: object, default: int, name: str) -> int:
    if value is None:
        return default
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _secret(value: object, name: str, *, required: bool = True) -> str:
    reference = str(value or "").strip()
    if not reference and not required:
        return ""
    if not reference.startswith("env://") or not reference.removeprefix("env://"):
        raise ValueError(f"{name} must be an env:// reference")
    secret = os.environ.get(reference.removeprefix("env://"), "").strip()
    if not secret:
        raise ValueError(f"{name} environment variable is empty")
    return secret


@dataclass(frozen=True, slots=True)
class FeishuApprovalSettings:
    eventd_endpoint: str
    raw_subscription_id: str
    eventd_token: str
    tenant_id: str
    app_id: str
    app_secret: str
    approval_codes: tuple[str, ...]
    instance_id: str = ""
    lease_seconds: int = 60
    renew_every_seconds: int = 20
    wait_seconds: int = 20
    callback_timeout_seconds: float = 2.5

    @property
    def source(self) -> str:
        return f"feishu://{self.tenant_id}/{self.app_id}/approval"


async def load_feishu_approval_config(path: str) -> FeishuApprovalSettings:
    if not path.strip():
        raise ValueError("Feishu approval adapter requires --config")
    raw = yaml.safe_load(await anyio.Path(path).read_text(encoding="utf-8"))
    root = _mapping(raw, "config")
    adapter = _mapping(root.get("feishuApprovalAdapter"), "feishuApprovalAdapter")

    endpoint = str(adapter.get("eventdEndpoint") or "").strip()
    subscription_id = str(adapter.get("rawSubscriptionId") or "").strip()
    tenant_id = str(adapter.get("tenantId") or "").strip()
    app_id = str(adapter.get("appId") or os.environ.get("PSI_FEISHU_APP_ID", "")).strip()
    if not endpoint or not subscription_id or not tenant_id or not app_id:
        raise ValueError("feishuApprovalAdapter requires eventdEndpoint, rawSubscriptionId, tenantId, and appId")

    raw_codes = adapter.get("approvalCodes")
    if not isinstance(raw_codes, list) or not raw_codes:
        raise ValueError("feishuApprovalAdapter.approvalCodes must be a non-empty list")
    if any(not isinstance(code, str) or not code.strip() for code in raw_codes):
        raise ValueError("feishuApprovalAdapter.approvalCodes must contain non-empty strings")
    approval_codes = tuple(dict.fromkeys(code.strip() for code in cast(list[str], raw_codes)))

    lease_seconds = _positive_int(adapter.get("leaseSeconds"), 60, "leaseSeconds")
    renew_seconds = _positive_int(adapter.get("renewEverySeconds"), 20, "renewEverySeconds")
    if renew_seconds >= lease_seconds:
        raise ValueError("feishuApprovalAdapter.renewEverySeconds must be less than leaseSeconds")
    wait_seconds = _positive_int(adapter.get("waitSeconds"), 20, "waitSeconds")

    callback_timeout = adapter.get("callbackTimeoutSeconds", 2.5)
    if (
        not isinstance(callback_timeout, (int, float))
        or isinstance(callback_timeout, bool)
        or callback_timeout <= 0
        or callback_timeout >= 3
    ):
        raise ValueError("feishuApprovalAdapter.callbackTimeoutSeconds must be greater than 0 and less than 3")

    return FeishuApprovalSettings(
        eventd_endpoint=endpoint,
        raw_subscription_id=subscription_id,
        eventd_token=_secret(
            adapter.get("eventdTokenRef"),
            "feishuApprovalAdapter.eventdTokenRef",
            required=False,
        ),
        tenant_id=tenant_id,
        app_id=app_id,
        app_secret=_secret(adapter.get("appSecretRef"), "feishuApprovalAdapter.appSecretRef"),
        approval_codes=approval_codes,
        instance_id=str(adapter.get("instanceId") or "").strip(),
        lease_seconds=lease_seconds,
        renew_every_seconds=renew_seconds,
        wait_seconds=wait_seconds,
        callback_timeout_seconds=float(callback_timeout),
    )
