"""CLI component for the standalone Feishu approval event adapter."""

from __future__ import annotations

from dataclasses import dataclass

from psi_agent._logging import setup_logging
from psi_agent.event_adapters.feishu.adapter import FeishuApprovalAdapterService
from psi_agent.event_adapters.feishu.config import load_feishu_approval_config


@dataclass
class FeishuApprovalAdapter:
    """Receive Feishu approval WebSocket events and emit generic CloudEvents."""

    config: str
    verbose: bool = False

    async def run(self) -> None:
        setup_logging(verbose=self.verbose)
        settings = await load_feishu_approval_config(self.config)
        await FeishuApprovalAdapterService(settings).run()
