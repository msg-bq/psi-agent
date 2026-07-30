"""Feishu WebSocket approval ingress for Event Daemon."""

from __future__ import annotations

import hashlib
import json
import random
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, cast

import anyio
from anyio.from_thread import BlockingPortal
from lark_channel import FeishuChannel, PolicyConfig
from lark_channel.core.enum import AccessTokenType, HttpMethod
from lark_channel.core.model import BaseRequest
from lark_channel.event.custom import CustomizedEventProcessor
from loguru import logger

from psi_agent.eventd.config import FeishuConnection
from psi_agent.eventd.schema import CloudEvent, EventConflictError
from psi_agent.eventd.server import EventService

_EVENT_TYPE = "approval_instance"


def _object_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return cast(dict[str, Any], value).copy()
    attrs = getattr(value, "__dict__", None)
    if isinstance(attrs, dict):
        return {str(key): item for key, item in attrs.items() if not str(key).startswith("_")}
    return {}


def _request(method: HttpMethod, uri: str) -> BaseRequest:
    req = BaseRequest()
    req.http_method = method
    req.uri = uri
    req.token_types = {AccessTokenType.TENANT}
    return req


def _response_body(response: Any) -> dict[str, Any]:
    raw = getattr(response, "raw", None)
    content = getattr(raw, "content", None) if raw is not None else None
    if not content:
        raise RuntimeError("Feishu response has no body")
    body = json.loads(bytes(content).decode("utf-8"))
    if not isinstance(body, dict) or body.get("code") != 0:
        raise RuntimeError(f"Feishu API error: {body}")
    return dict(body)


def _response_data(response: Any) -> dict[str, Any]:
    body = _response_body(response)
    data = body.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("Feishu response data must be an object")
    return dict(data)


def _register_processor(channel: Any, on_event: Any) -> None:
    dispatcher = getattr(channel, "dispatcher", None)
    processors = getattr(dispatcher, "_processorMap", None)
    if not isinstance(processors, dict):
        raise RuntimeError("Feishu dispatcher has no customized-event processor map")
    registered = 0
    for schema in ("p1", "p2"):
        key = f"{schema}.{_EVENT_TYPE}"
        if key not in processors:
            processors[key] = CustomizedEventProcessor(on_event)
            registered += 1
    logger.info(f"Event Daemon registered {registered} Feishu approval processor(s)")


def _attachments(form: object) -> list[dict[str, Any]]:
    if not isinstance(form, list):
        return []
    attachments: list[dict[str, Any]] = []
    for widget in form:
        if not isinstance(widget, dict):
            continue
        widget_type = str(widget.get("type") or "").casefold()
        name = widget.get("name") or widget.get("id") or ""
        value = widget.get("value")
        values = value if isinstance(value, list) else [value]
        if "document" in widget_type:
            kind = "drive"
        elif any(part in widget_type for part in ("attachment", "image", "file")):
            kind = "url"
        else:
            continue
        for item in values:
            if item:
                attachments.append({"name": name, "type": widget.get("type", ""), "kind": kind, "value": item})
    return attachments


@dataclass(slots=True)
class FeishuApprovalIngress:
    service: EventService
    connection: FeishuConnection
    channel: Any

    async def persist_raw(self, event: Any) -> tuple[str, dict[str, Any], str]:
        payload = _object_dict(getattr(event, "event", None))
        if not payload:
            payload = _object_dict(event).get("event", {})
        if not isinstance(payload, dict):
            raise ValueError("Feishu approval event has no object payload")
        header = _object_dict(getattr(event, "header", None))
        event_id = str(header.get("event_id") or header.get("event_id_v2") or "").strip()
        receipt_id = await self.service.store.receive_raw(
            provider="feishu",
            connection_id=self.connection.id,
            transport="websocket",
            provider_event_id=event_id,
            raw_payload={"event": payload, "header": header},
        )
        await self.service.store.set_connection_state(
            self.connection.id, "last_received_ms", str(time.time_ns() // 1_000_000)
        )
        return receipt_id, payload, event_id

    async def receive(self, event: Any) -> None:
        receipt_id, payload, event_id = await self.persist_raw(event)
        await self.normalize(receipt_id, payload, event_id)

    async def normalize(
        self,
        receipt_id: str,
        payload: dict[str, Any],
        provider_event_id: str,
        previous_attempts: int = 0,
    ) -> None:
        await self.service.store.set_raw_state(receipt_id, "NORMALIZING")
        approval_code = str(payload.get("approval_code") or "").strip()
        instance_code = str(payload.get("instance_code") or "").strip()
        if not instance_code:
            await self.service.store.set_raw_state(receipt_id, "ADAPTER_DEAD", "missing instance_code")
            return
        if self.connection.approval_codes and approval_code not in self.connection.approval_codes:
            await self.service.store.set_raw_state(receipt_id, "IGNORED")
            return
        try:
            detail = await self._fetch_detail(instance_code)
            event = self._cloud_event(payload, detail, provider_event_id)
            await self.service.accept(event)
        except EventConflictError as e:
            await self.service.store.set_raw_state(receipt_id, "ADAPTER_DEAD", str(e))
            logger.error(f"Feishu approval conflict receipt={receipt_id}: {e}")
            return
        except Exception as e:
            next_state = "ADAPTER_DEAD" if previous_attempts + 1 >= 10 else "NORMALIZE_RETRY"
            await self.service.store.set_raw_state(receipt_id, next_state, str(e))
            logger.warning(f"Feishu approval enrichment retry receipt={receipt_id}: {e!r}")
            return
        await self.service.store.set_raw_state(receipt_id, "AVAILABLE")
        logger.info(f"Feishu approval persisted instance={instance_code} event={event.id}")

    async def retry_pending(self) -> None:
        while True:
            rows = await self.service.store.pending_raw(self.connection.id)
            for row in rows:
                raw = row["raw_payload"]
                payload = raw.get("event", {}) if isinstance(raw, dict) else {}
                if not isinstance(payload, dict):
                    await self.service.store.set_raw_state(row["receipt_id"], "ADAPTER_DEAD", "invalid raw event")
                    continue
                await self.normalize(
                    row["receipt_id"],
                    payload,
                    str(row["provider_event_id"]),
                    int(row["normalize_attempts"]),
                )
            await anyio.sleep(5)

    async def ensure_subscriptions(self) -> None:
        for approval_code in self.connection.approval_codes:
            req = _request(HttpMethod.POST, "/open-apis/approval/v4/approvals/:approval_code/subscribe")
            req.paths["approval_code"] = approval_code
            response = await self.channel.client.arequest(req)
            _response_body(response)
            logger.info(f"Feishu approval subscription confirmed code={approval_code!r}")

    async def reconcile_loop(self) -> None:
        if not self.connection.reconciliation_enabled:
            return
        while True:
            try:
                await self.reconcile_once()
            except Exception as e:
                logger.warning(f"Feishu reconciliation failed connection={self.connection.id!r}: {e!r}")
            await anyio.sleep(self.connection.reconciliation_interval_seconds)

    async def reconcile_once(self) -> None:
        end_ms = time.time_ns() // 1_000_000
        saved = await self.service.store.get_connection_state(self.connection.id, "reconcile_last_ms")
        last_ms = int(saved) if saved.isdigit() else end_ms
        start_ms = max(0, last_ms - self.connection.reconciliation_overlap_seconds * 1000)
        for approval_code in self.connection.approval_codes:
            for instance_code in await self._list_instances(approval_code, start_ms, end_ms):
                detail = await self._fetch_detail(instance_code)
                payload = {
                    "approval_code": approval_code,
                    "instance_code": instance_code,
                    "status": detail.get("status", ""),
                    "instance_operate_time": detail.get("instance_operate_time", ""),
                }
                receipt_id = await self.service.store.receive_raw(
                    provider="feishu",
                    connection_id=self.connection.id,
                    transport="reconciliation",
                    provider_event_id="",
                    raw_payload={"event": payload, "reconciled": True},
                )
                event = self._cloud_event(payload, detail, "")
                if await self.service.store.contains_event(event.source, event.id):
                    await self.service.store.set_raw_state(receipt_id, "AVAILABLE")
                    continue
                try:
                    await self.service.accept(event)
                except EventConflictError as e:
                    await self.service.store.set_raw_state(receipt_id, "ADAPTER_DEAD", str(e))
                else:
                    await self.service.store.set_raw_state(receipt_id, "AVAILABLE")
        await self.service.store.set_connection_state(self.connection.id, "reconcile_last_ms", str(end_ms))
        logger.info(f"Feishu reconciliation complete connection={self.connection.id!r} window={start_ms}..{end_ms}")

    async def _list_instances(self, approval_code: str, start_ms: int, end_ms: int) -> list[str]:
        codes: list[str] = []
        page_token = ""
        while True:
            req = _request(HttpMethod.GET, "/open-apis/approval/v4/instances")
            req.add_query("approval_code", approval_code)
            req.add_query("start_time", str(start_ms))
            req.add_query("end_time", str(end_ms))
            req.add_query("page_size", 100)
            if page_token:
                req.add_query("page_token", page_token)
            data = _response_data(await self.channel.client.arequest(req))
            chunk = data.get("instance_code_list", [])
            if isinstance(chunk, list):
                codes.extend(str(item) for item in chunk if item)
            page_token = str(data.get("page_token") or "")
            if not data.get("has_more") or not page_token:
                return codes

    async def _fetch_detail(self, instance_code: str) -> dict[str, Any]:
        req = _request(HttpMethod.GET, "/open-apis/approval/v4/instances/:instance_id")
        req.paths["instance_id"] = instance_code
        req.add_query("user_id_type", "open_id")
        response = await self.channel.client.arequest(req)
        detail = _response_data(response)
        for name in ("form", "task_list", "timeline"):
            value = detail.get(name)
            if isinstance(value, str):
                with suppress(json.JSONDecodeError):
                    detail[name] = json.loads(value)
        return detail

    def _cloud_event(
        self,
        payload: dict[str, Any],
        detail: dict[str, Any],
        provider_event_id: str,
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
        stable = "|".join((self.connection.tenant_id, approval_code, instance_code, status, operate_time))
        event_id = hashlib.sha256(stable.encode()).hexdigest()
        data = dict(detail)
        data.update(
            {
                "approval_code": approval_code,
                "instance_code": instance_code,
                "approval_name": detail.get("approval_name", ""),
                "status": status,
                "instance_operate_time": operate_time,
                "applicant": detail.get("user_id", "") or detail.get("open_id", ""),
                "form": detail.get("form", []),
                "attachments": detail.get("attachments") or _attachments(detail.get("form")),
                "task_list": detail.get("task_list", []),
                "timeline": detail.get("timeline", []),
            }
        )
        return CloudEvent(
            specversion="1.0",
            id=event_id,
            source=f"feishu://{self.connection.tenant_id}/{self.connection.app_id}/approval",
            type="approval.status.changed",
            data=data,
        )


async def _run_connection_once(service: EventService, connection: FeishuConnection) -> None:
    policy = PolicyConfig(require_mention=True, respond_to_mention_all=False)
    channel = FeishuChannel(app_id=connection.app_id, app_secret=connection.app_secret, policy=policy)
    ingress = FeishuApprovalIngress(service, connection, channel)
    async with BlockingPortal() as portal:

        def on_event(event: Any) -> None:
            try:
                receipt_id, payload, event_id = portal.call(ingress.persist_raw, event)
                portal.start_task_soon(ingress.normalize, receipt_id, payload, event_id)
            except Exception as e:
                logger.error(f"Feishu raw event persistence failed before SDK callback returned: {e!r}")
                raise

        try:
            await channel.start_background()
            _register_processor(channel, on_event)
            await ingress.ensure_subscriptions()
            await service.store.set_connection_state(connection.id, "websocket", "connected")
            await service.store.set_connection_state(
                connection.id, "last_connected_ms", str(time.time_ns() // 1_000_000)
            )
            logger.info(f"Feishu Event Daemon connection {connection.id!r} started")
            async with anyio.create_task_group() as tg:
                tg.start_soon(ingress.retry_pending)
                tg.start_soon(ingress.reconcile_loop)
                await anyio.sleep_forever()
        finally:
            with anyio.CancelScope(shield=True):
                try:
                    await service.store.set_connection_state(connection.id, "websocket", "disconnected")
                except Exception as e:
                    logger.warning(f"Feishu connection state cleanup failed: {e!r}")
                try:
                    await channel.stop_background()
                except Exception as e:
                    logger.warning(f"Feishu Event Daemon stop failed: {e!r}")


async def _supervise_connection(service: EventService, connection: FeishuConnection) -> None:
    failures = 0
    while True:
        try:
            await _run_connection_once(service, connection)
            raise RuntimeError("Feishu connection stopped unexpectedly")
        except Exception as e:
            failures += 1
            delay = min(60.0, 1.0 * (2 ** min(failures - 1, 6)))
            delay *= random.uniform(0.8, 1.2)
            await service.store.set_connection_state(connection.id, "websocket", "reconnecting")
            await service.store.set_connection_state(connection.id, "reconnect_count", str(failures))
            await service.store.set_connection_state(connection.id, "last_error", str(e)[:1000])
            logger.warning(f"Feishu connection {connection.id!r} failed; retrying in {delay:.1f}s: {e!r}")
            await anyio.sleep(delay)


async def run_feishu_connections(service: EventService, connections: tuple[FeishuConnection, ...]) -> None:
    for connection in connections:
        if connection.transport != "websocket":
            logger.warning(f"Feishu connection {connection.id!r} uses webhook; endpoint adapter is not enabled yet")
    websocket_connections = tuple(connection for connection in connections if connection.transport == "websocket")
    if not websocket_connections:
        logger.info("Event Daemon has no Feishu WebSocket connections")
        return
    async with anyio.create_task_group() as tg:
        for connection in websocket_connections:
            tg.start_soon(_supervise_connection, service, connection)
