"""Standalone Feishu WebSocket approval adapter and normalization worker."""

from __future__ import annotations

import hashlib
import json
import random
import uuid
from dataclasses import dataclass, field
from typing import Any, cast

import anyio
from anyio.from_thread import BlockingPortal
from lark_channel import FeishuChannel, PolicyConfig
from loguru import logger

from psi_agent.event_adapters.feishu.config import FeishuApprovalSettings
from psi_agent.event_adapters.feishu.eventd_client import EventdClient
from psi_agent.event_adapters.feishu.sdk import FeishuApprovalApi, object_dict, register_approval_processor
from psi_agent.eventd.schema import CloudEvent

_RAW_EVENT_TYPE = "feishu.approval.instance.received"
_NORMALIZED_EVENT_TYPE = "approval.status.changed"


@dataclass(slots=True)
class FeishuApprovalAdapterService:
    settings: FeishuApprovalSettings
    _eventd: EventdClient | None = field(init=False, default=None)
    _api: FeishuApprovalApi | None = field(init=False, default=None)

    async def run(self) -> None:
        async with EventdClient(self.settings.eventd_endpoint, self.settings.eventd_token) as eventd:
            self._eventd = eventd
            try:
                async with anyio.create_task_group() as task_group:
                    task_group.start_soon(self._supervise_websocket)
                    task_group.start_soon(self._normalize_loop)
            finally:
                self._eventd = None

    async def persist_raw(self, event: Any) -> CloudEvent:
        payload = object_dict(getattr(event, "event", None))
        if not payload:
            candidate = object_dict(event).get("event")
            payload = cast(dict[str, Any], candidate) if isinstance(candidate, dict) else {}
        if not payload:
            raise ValueError("Feishu approval event has no object payload")
        header = object_dict(getattr(event, "header", None))
        provider_event_id = str(header.get("event_id") or header.get("event_id_v2") or "").strip()
        if provider_event_id:
            event_id = provider_event_id
        else:
            canonical = json.dumps(
                {"header": header, "event": payload},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            event_id = hashlib.sha256(canonical.encode()).hexdigest()
        raw_event = CloudEvent(
            specversion="1.0",
            id=event_id,
            source=f"{self.settings.source}/raw",
            type=_RAW_EVENT_TYPE,
            data={"header": header, "event": payload},
        )
        eventd = self._require_eventd()
        status = await eventd.publish(
            raw_event,
            timeout_seconds=self.settings.callback_timeout_seconds,
        )
        logger.info(f"Feishu raw approval persisted id={event_id!r} status={status}")
        return raw_event

    async def _supervise_websocket(self) -> None:
        failures = 0
        while True:
            try:
                await self._run_websocket_once()
                raise RuntimeError("Feishu WebSocket stopped unexpectedly")
            except Exception as e:
                failures += 1
                delay = min(60.0, float(2 ** min(failures - 1, 6)))
                delay *= random.uniform(0.8, 1.2)
                logger.warning(f"Feishu approval WebSocket failed; retrying in {delay:.1f}s: {e!r}")
                await anyio.sleep(delay)

    async def _run_websocket_once(self) -> None:
        policy = PolicyConfig(require_mention=True, respond_to_mention_all=False)
        channel = FeishuChannel(
            app_id=self.settings.app_id,
            app_secret=self.settings.app_secret,
            policy=policy,
        )
        async with BlockingPortal() as portal:

            def on_event(event: Any) -> None:
                portal.call(self.persist_raw, event)

            try:
                await channel.start_background()
                register_approval_processor(channel, on_event)
                api = FeishuApprovalApi(channel)
                self._api = api
                await api.ensure_subscriptions(self.settings.approval_codes)
                logger.info(
                    f"Feishu approval adapter connected app={self.settings.app_id!r} "
                    f"approvals={len(self.settings.approval_codes)}"
                )
                await anyio.sleep_forever()
            finally:
                self._api = None
                with anyio.CancelScope(shield=True):
                    try:
                        await channel.stop_background()
                    except Exception as e:
                        logger.warning(f"Feishu approval WebSocket stop failed: {e!r}")

    async def _normalize_loop(self) -> None:
        instance_id = self.settings.instance_id or f"feishu-approval/{uuid.uuid4()}"
        failures = 0
        while True:
            try:
                deliveries = await self._require_eventd().claim(
                    self.settings.raw_subscription_id,
                    instance_id=instance_id,
                    lease_seconds=self.settings.lease_seconds,
                    wait_seconds=self.settings.wait_seconds,
                )
                for delivery in deliveries:
                    await self._process_delivery(delivery)
                failures = 0
            except Exception as e:
                failures += 1
                delay = min(30.0, float(2 ** min(failures - 1, 5)))
                logger.warning(f"Feishu approval normalizer failed; retrying in {delay:.1f}s: {e!r}")
                await anyio.sleep(delay)

    async def _process_delivery(self, delivery: dict[str, Any]) -> None:
        delivery_id = str(delivery.get("deliveryId") or "").strip()
        lease_token = str(delivery.get("leaseToken") or "").strip()
        if not delivery_id or not lease_token:
            raise ValueError("raw delivery is missing deliveryId or leaseToken")
        try:
            raw_event = CloudEvent.parse(delivery.get("event"))
            normalized: CloudEvent | None = None
            normalization_error: Exception | None = None
            async with anyio.create_task_group() as task_group:
                task_group.start_soon(self._renew_loop, delivery_id, lease_token)
                try:
                    normalized = await self.normalize(raw_event)
                    if normalized is not None:
                        status = await self._require_eventd().publish(normalized)
                        logger.info(
                            f"Feishu approval normalized raw={raw_event.id!r} event={normalized.id!r} status={status}"
                        )
                except Exception as e:
                    normalization_error = e
                finally:
                    task_group.cancel_scope.cancel()
            if normalization_error is not None:
                raise normalization_error
        except Exception as e:
            logger.warning(f"Feishu raw delivery {delivery_id} normalization failed: {e!r}")
            await self._nack(delivery_id, lease_token, str(e))
            return
        await self._require_eventd().control(delivery_id, "ack", {"leaseToken": lease_token})

    async def normalize(self, raw_event: CloudEvent) -> CloudEvent | None:
        if raw_event.type != _RAW_EVENT_TYPE or raw_event.source != f"{self.settings.source}/raw":
            raise ValueError("raw delivery does not belong to this Feishu approval adapter")
        if not isinstance(raw_event.data, dict):
            raise ValueError("raw Feishu approval data must be an object")
        payload = raw_event.data.get("event")
        if not isinstance(payload, dict):
            raise ValueError("raw Feishu approval event payload must be an object")
        approval_code = str(payload.get("approval_code") or "").strip()
        if approval_code not in self.settings.approval_codes:
            logger.info(f"Ignoring unconfigured Feishu approval code={approval_code!r}")
            return None
        instance_code = str(payload.get("instance_code") or "").strip()
        if not instance_code:
            raise ValueError("Feishu approval event is missing instance_code")
        api = self._api
        if api is None:
            raise RuntimeError("Feishu approval API is unavailable while WebSocket reconnects")
        detail = await api.fetch_detail(instance_code)
        return self._normalized_event(cast(dict[str, Any], payload), detail)

    def _normalized_event(
        self,
        payload: dict[str, Any],
        detail: dict[str, Any],
    ) -> CloudEvent:
        approval_code = str(payload.get("approval_code") or detail.get("approval_code") or "")
        instance_code = str(payload.get("instance_code") or detail.get("instance_code") or "")
        status = str(payload.get("status") or detail.get("status") or "")
        operate_time = str(
            payload.get("instance_operate_time")
            or payload.get("operate_time")
            or detail.get("instance_operate_time")
            or ""
        )
        identity = "|".join((self.settings.tenant_id, approval_code, instance_code, status, operate_time))
        event_id = hashlib.sha256(identity.encode()).hexdigest()
        data = detail.copy()
        data.update(
            {
                "approval_code": approval_code,
                "instance_code": instance_code,
                "approval_name": detail.get("approval_name") or "",
                "status": status,
                "instance_operate_time": operate_time,
                "applicant": detail.get("user_id") or detail.get("open_id") or "",
                "form": detail.get("form") or [],
                "attachments": detail.get("attachments") or self._attachments(detail.get("form")),
                "task_list": detail.get("task_list") or [],
                "timeline": detail.get("timeline") or [],
            }
        )
        return CloudEvent("1.0", event_id, self.settings.source, _NORMALIZED_EVENT_TYPE, data)

    @staticmethod
    def _attachments(form: object) -> list[dict[str, Any]]:
        if not isinstance(form, list):
            return []
        attachments: list[dict[str, Any]] = []
        for widget in form:
            if not isinstance(widget, dict):
                continue
            widget_type = str(widget.get("type") or "").casefold()
            values = widget.get("value")
            items = values if isinstance(values, list) else [values]
            if "document" in widget_type:
                kind = "drive"
            elif any(part in widget_type for part in ("attachment", "image", "file")):
                kind = "url"
            else:
                continue
            for item in items:
                if item:
                    attachments.append(
                        {
                            "name": widget.get("name") or widget.get("id") or "",
                            "type": widget.get("type") or "",
                            "kind": kind,
                            "value": item,
                        }
                    )
        return attachments

    async def _renew_loop(self, delivery_id: str, lease_token: str) -> None:
        while True:
            await anyio.sleep(self.settings.renew_every_seconds)
            await self._require_eventd().control(
                delivery_id,
                "renew",
                {
                    "leaseToken": lease_token,
                    "leaseSeconds": self.settings.lease_seconds,
                },
            )

    async def _nack(self, delivery_id: str, lease_token: str, error: str) -> None:
        try:
            await self._require_eventd().control(
                delivery_id,
                "nack",
                {
                    "leaseToken": lease_token,
                    "error": error,
                    "retrySeconds": 5,
                },
            )
        except Exception as e:
            logger.warning(f"Feishu raw delivery {delivery_id} NACK failed: {e!r}")

    def _require_eventd(self) -> EventdClient:
        if self._eventd is None:
            raise RuntimeError("Feishu approval adapter is not connected to Event Daemon")
        return self._eventd
