"""Lease-based Event Daemon consumer that dispatches into Session ``/events``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from psi_agent.channel._core import ChannelCore
from psi_agent.eventd.client import Delivery, EventdClient
from psi_agent.eventd.schema import cloud_event_to_session_envelope
from psi_agent.eventd.worker import LeaseWorker


class ConsumerError(RuntimeError):
    """A durable delivery could not be safely completed."""


@dataclass(slots=True)
class EventConsumerWorker:
    daemon_endpoint: str
    subscription_id: str
    session_socket: str
    instance_id: str = ""
    renew_every_seconds: int = 20
    lease_seconds: int = 0
    wait_seconds: int = 20
    api_token: str = ""
    routing: dict[str, Any] | None = None

    async def run(self) -> None:
        async with (
            EventdClient(self.daemon_endpoint, self.api_token) as client,
            ChannelCore(self.session_socket, interval=0) as core,
        ):

            async def dispatch(delivery: Delivery) -> None:
                event = delivery.event
                delivery_id = delivery.delivery_id
                event_routing = dict(self.routing or {})
                event_routing.update(
                    {
                        "delivery_id": delivery_id,
                        "event_source": event.source,
                        "event_id": event.id,
                        "subscription_id": self.subscription_id,
                    }
                )
                result = await core.post_event(cloud_event_to_session_envelope(event, routing=event_routing))
                if result is None:
                    raise ConsumerError("Session returned no result")
                fired = result.get("fired")
                failed = result.get("failed")
                duplicate = result.get("duplicate") is True
                succeeded = result.get("ok") is True and isinstance(fired, list) and bool(fired) and not failed
                if succeeded or (result.get("ok") is True and duplicate):
                    return
                matched = result.get("matched")
                raise ConsumerError(
                    f"Session did not complete delivery: matched={matched!r} fired={fired!r} failed={failed!r}"
                )

            worker = LeaseWorker(
                client=client,
                subscription_id=self.subscription_id,
                handler=dispatch,
                instance_id=self.instance_id,
                renew_every_seconds=self.renew_every_seconds,
                lease_seconds=self.lease_seconds,
                wait_seconds=self.wait_seconds,
            )
            await worker.run()
