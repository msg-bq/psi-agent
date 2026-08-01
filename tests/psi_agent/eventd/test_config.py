from __future__ import annotations

from pathlib import Path

import anyio
import pytest

from psi_agent.eventd.config import load_consumer_config, load_daemon_config


@pytest.mark.anyio
async def test_daemon_config_uses_environment_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FEISHU_SECRET_FOR_TEST", "secret")
    path = tmp_path / "eventd.yml"
    await anyio.Path(path).write_text(
        """\
daemon:
  listen: http://127.0.0.1:9999
connections:
  - id: finance
    provider: feishu
    transport: websocket
    tenantId: tenant
    appId: app
    appSecretRef: env://FEISHU_SECRET_FOR_TEST
    approvalCodes: [expense]
subscriptions:
  - id: finance-agent
    filter:
      types: [approval.status.changed]
""",
        encoding="utf-8",
    )
    config = await load_daemon_config(
        path=str(path), listen="", data_path=str(tmp_path / "events.sqlite3"), appdata="", api_token=""
    )
    assert config.connections[0].app_secret == "secret"
    assert config.subscriptions[0].types == ("approval.status.changed",)


@pytest.mark.anyio
async def test_consumer_renewal_must_precede_lease_expiry() -> None:
    with pytest.raises(ValueError, match="renewEverySeconds"):
        await load_consumer_config(
            path="",
            daemon_endpoint="http://127.0.0.1:8765",
            subscription_id="finance",
            session_socket="http://127.0.0.1:9000",
            instance_id="",
            renew_every_seconds=60,
            lease_seconds=60,
            wait_seconds=20,
            api_token="",
        )


@pytest.mark.anyio
async def test_non_loopback_daemon_requires_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PSI_EVENTD_TOKEN", raising=False)
    with pytest.raises(ValueError, match="non-loopback"):
        await load_daemon_config(
            path="",
            listen="http://0.0.0.0:8765",
            data_path=str(tmp_path / "events.sqlite3"),
            appdata=str(tmp_path / "appdata"),
            api_token="",
        )
