"""Narrow compatibility layer around ``lark-channel-sdk`` approval APIs."""

from __future__ import annotations

import json
import math
from contextlib import suppress
from typing import Any, cast

from lark_channel.core.enum import AccessTokenType, HttpMethod
from lark_channel.core.model import BaseRequest
from lark_channel.event.custom import CustomizedEventProcessor


def json_value(value: object) -> Any:
    """Convert SDK model objects into finite JSON without provider types leaking out."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    attrs = getattr(value, "__dict__", None)
    if isinstance(attrs, dict):
        return {str(key): json_value(item) for key, item in attrs.items() if not str(key).startswith("_")}
    return str(value)


def object_dict(value: object) -> dict[str, Any]:
    converted = json_value(value)
    if isinstance(converted, dict):
        return cast(dict[str, Any], converted)
    return {}


def register_approval_processor(channel: Any, on_event: Any) -> None:
    """Register the SDK's missing typed processor after ``start_background``."""
    dispatcher = getattr(channel, "dispatcher", None)
    processors = getattr(dispatcher, "_processorMap", None)
    if not isinstance(processors, dict):
        raise RuntimeError("lark-channel-sdk is incompatible: dispatcher._processorMap is unavailable")
    for schema in ("p1", "p2"):
        key = f"{schema}.approval_instance"
        if key not in processors:
            processors[key] = CustomizedEventProcessor(on_event)


class FeishuApprovalApi:
    def __init__(self, channel: Any) -> None:
        self._channel = channel

    @staticmethod
    def _request(method: HttpMethod, uri: str) -> BaseRequest:
        request = BaseRequest()
        request.http_method = method
        request.uri = uri
        request.token_types = {AccessTokenType.TENANT}
        return request

    @staticmethod
    def _body(response: Any) -> dict[str, Any]:
        raw = getattr(response, "raw", None)
        content = getattr(raw, "content", None) if raw is not None else None
        if not content:
            raise RuntimeError("Feishu response has no body")
        body = json.loads(bytes(content).decode("utf-8"))
        if not isinstance(body, dict) or body.get("code") != 0:
            raise RuntimeError(f"Feishu API error: {body}")
        return cast(dict[str, Any], body)

    @classmethod
    def _data(cls, response: Any) -> dict[str, Any]:
        data = cls._body(response).get("data")
        if not isinstance(data, dict):
            raise RuntimeError("Feishu response data must be an object")
        return cast(dict[str, Any], data).copy()

    async def ensure_subscriptions(self, approval_codes: tuple[str, ...]) -> None:
        for approval_code in approval_codes:
            request = self._request(
                HttpMethod.POST,
                "/open-apis/approval/v4/approvals/:approval_code/subscribe",
            )
            request.paths["approval_code"] = approval_code
            self._body(await self._channel.client.arequest(request))

    async def fetch_detail(self, instance_code: str) -> dict[str, Any]:
        request = self._request(HttpMethod.GET, "/open-apis/approval/v4/instances/:instance_id")
        request.paths["instance_id"] = instance_code
        request.add_query("user_id_type", "open_id")
        detail = self._data(await self._channel.client.arequest(request))
        for name in ("form", "task_list", "timeline"):
            value = detail.get(name)
            if isinstance(value, str):
                with suppress(json.JSONDecodeError):
                    detail[name] = json.loads(value)
        return detail
