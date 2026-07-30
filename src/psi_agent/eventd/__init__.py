"""Independent Event Daemon and durable Event Consumer CLI components."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial

import anyio
from loguru import logger

from psi_agent._logging import setup_logging
from psi_agent.eventd.adapters.feishu import run_feishu_connections
from psi_agent.eventd.config import load_consumer_config, load_daemon_config
from psi_agent.eventd.consumer import EventConsumerWorker
from psi_agent.eventd.server import EventService, serve_eventd
from psi_agent.eventd.store import EventStore


@dataclass
class EventDaemon:
    """Run the independent durable event receiver and lease queue."""

    config: str = ""
    listen: str = "http://127.0.0.1:8765"
    data_path: str = ""
    appdata: str = ""
    api_token: str = ""
    verbose: bool = False

    async def run(self) -> None:
        setup_logging(verbose=self.verbose)
        settings = await load_daemon_config(
            path=self.config,
            listen=self.listen,
            data_path=self.data_path,
            appdata=self.appdata,
            api_token=self.api_token,
        )
        store = EventStore(settings.data_path)
        service = EventService(store, settings.subscriptions)
        await service.initialize()
        logger.info(
            f"Event Daemon database={settings.data_path!r} subscriptions={len(settings.subscriptions)} "
            f"connections={len(settings.connections)}"
        )

        async with anyio.create_task_group() as tg:
            tg.start_soon(partial(serve_eventd, service, listen=settings.listen, api_token=settings.api_token))
            tg.start_soon(run_feishu_connections, service, settings.connections)


@dataclass
class EventConsumer:
    """Claim Event Daemon deliveries and synchronously dispatch them to Session."""

    session_socket: str = ""
    config: str = ""
    daemon_endpoint: str = "http://127.0.0.1:8765"
    subscription_id: str = "haitun-events"
    instance_id: str = ""
    renew_every_seconds: int = 20
    lease_seconds: int = 60
    wait_seconds: int = 20
    api_token: str = ""
    verbose: bool = False

    async def run(self) -> None:
        setup_logging(verbose=self.verbose)
        settings = await load_consumer_config(
            path=self.config,
            daemon_endpoint=self.daemon_endpoint,
            subscription_id=self.subscription_id,
            session_socket=self.session_socket,
            instance_id=self.instance_id,
            renew_every_seconds=self.renew_every_seconds,
            lease_seconds=self.lease_seconds,
            wait_seconds=self.wait_seconds,
            api_token=self.api_token,
        )
        worker = EventConsumerWorker(
            daemon_endpoint=settings.daemon_endpoint,
            subscription_id=settings.subscription_id,
            session_socket=settings.session_socket,
            instance_id=settings.instance_id,
            renew_every_seconds=settings.renew_every_seconds,
            lease_seconds=settings.lease_seconds,
            wait_seconds=settings.wait_seconds,
            api_token=settings.api_token,
            routing=settings.routing,
        )
        await worker.run()
