from __future__ import annotations

from pathlib import Path

import anyio
import pytest

from psi_agent.eventd.config import load_consumer_config, load_daemon_config


@pytest.mark.anyio
async def test_daemon_config_uses_provider_neutral_default_subscription(tmp_path: Path) -> None:
    config = await load_daemon_config(
        path="",
        listen="http://127.0.0.1:8765",
        data_path=str(tmp_path / "events.sqlite3"),
        appdata="",
        api_token="",
    )
    assert [subscription.id for subscription in config.subscriptions] == ["default"]


@pytest.mark.anyio
async def test_daemon_config_loads_generic_hook(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOOK_SECRET_FOR_TEST", "secret")
    path = tmp_path / "eventd.yml"
    await anyio.Path(path).write_text(
        """\
daemon:
  listen: http://127.0.0.1:9999
hooks:
  - id: orders
    tokenRef: env://HOOK_SECRET_FOR_TEST
    source: webhook://orders
    type: order.received
    idFrom:
      header: X-Event-Id
subscriptions:
  - id: order-agent
    filter:
      types: [order.received]
""",
        encoding="utf-8",
    )
    config = await load_daemon_config(
        path=str(path), listen="", data_path=str(tmp_path / "events.sqlite3"), appdata="", api_token=""
    )
    assert config.hooks[0].token == "secret"
    assert config.hooks[0].id_header == "X-Event-Id"
    assert config.subscriptions[0].types == ("order.received",)


@pytest.mark.anyio
async def test_hook_rejects_literal_or_ambiguous_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOOK_SECRET_FOR_TEST", "secret")
    path = tmp_path / "eventd.yml"
    await anyio.Path(path).write_text(
        """\
hooks:
  - id: orders
    tokenRef: env://HOOK_SECRET_FOR_TEST
    token: leaked
    idFrom:
      header: X-Event-Id
      pointer: /id
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="cannot contain a secret"):
        await load_daemon_config(
            path=str(path),
            listen="http://127.0.0.1:8765",
            data_path=str(tmp_path / "events.sqlite3"),
            appdata="",
            api_token="",
        )


@pytest.mark.anyio
async def test_consumer_renewal_must_precede_lease_expiry() -> None:
    with pytest.raises(ValueError, match="renewEverySeconds"):
        await load_consumer_config(
            path="",
            daemon_endpoint="http://127.0.0.1:8765",
            subscription_id="orders",
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
