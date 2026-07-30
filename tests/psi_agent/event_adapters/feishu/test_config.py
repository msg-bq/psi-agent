from __future__ import annotations

from pathlib import Path

import anyio
import pytest

from psi_agent.event_adapters.feishu.config import load_feishu_approval_config


@pytest.mark.anyio
async def test_load_config_uses_env_only_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FEISHU_ADAPTER_SECRET", "app-secret")
    monkeypatch.setenv("EVENTD_ADAPTER_TOKEN", "eventd-token")
    path = tmp_path / "adapter.yml"
    await anyio.Path(path).write_text(
        """\
feishuApprovalAdapter:
  eventdEndpoint: http://127.0.0.1:8765
  rawSubscriptionId: feishu-approval-normalizer
  eventdTokenRef: env://EVENTD_ADAPTER_TOKEN
  tenantId: tenant-a
  appId: cli_adapter
  appSecretRef: env://FEISHU_ADAPTER_SECRET
  approvalCodes: [expense, expense, travel]
""",
        encoding="utf-8",
    )

    config = await load_feishu_approval_config(str(path))

    assert config.app_secret == "app-secret"
    assert config.eventd_token == "eventd-token"
    assert config.approval_codes == ("expense", "travel")
    assert config.source == "feishu://tenant-a/cli_adapter/approval"
    assert config.callback_timeout_seconds == 2.5


@pytest.mark.anyio
async def test_callback_timeout_must_stay_below_feishu_deadline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FEISHU_ADAPTER_SECRET", "app-secret")
    monkeypatch.setenv("EVENTD_ADAPTER_TOKEN", "eventd-token")
    path = tmp_path / "adapter.yml"
    await anyio.Path(path).write_text(
        """\
feishuApprovalAdapter:
  eventdEndpoint: http://127.0.0.1:8765
  rawSubscriptionId: raw
  eventdTokenRef: env://EVENTD_ADAPTER_TOKEN
  tenantId: tenant-a
  appId: cli_adapter
  appSecretRef: env://FEISHU_ADAPTER_SECRET
  approvalCodes: [expense]
  callbackTimeoutSeconds: 3
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="less than 3"):
        await load_feishu_approval_config(str(path))
