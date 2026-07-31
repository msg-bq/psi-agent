from __future__ import annotations

from pathlib import Path

import anyio
import pytest

from psi_agent.session import Session
from psi_agent.session.conversation import Conversation
from psi_agent.session.schedule_registry import ACTIVATE_ALL
from psi_agent.session.system_prompt import SystemPrompt


@pytest.mark.anyio
async def test_system_py_not_exists(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    await anyio.Path(ws).mkdir()
    sp = await SystemPrompt.from_workspace(ws, "test")
    assert await sp._builder() == ""


@pytest.mark.anyio
async def test_system_py_missing_system_prompt_builder(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    systems = ws / "systems"
    await anyio.Path(systems).mkdir(parents=True)
    await anyio.Path(systems / "system.py").write_text("def unrelated():\n    pass", encoding="utf-8")
    sp = await SystemPrompt.from_workspace(ws, "test")
    assert await sp._builder() == ""


@pytest.mark.anyio
async def test_system_prompt_builder_not_async(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    systems = ws / "systems"
    await anyio.Path(systems).mkdir(parents=True)
    await anyio.Path(systems / "system.py").write_text(
        "def system_prompt_builder():\n    return 'hello'", encoding="utf-8"
    )
    sp = await SystemPrompt.from_workspace(ws, "test")
    assert await sp._builder() == ""


@pytest.mark.anyio
async def test_system_prompt_builder_loads(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    systems = ws / "systems"
    await anyio.Path(systems).mkdir(parents=True)
    await anyio.Path(systems / "system.py").write_text(
        "async def system_prompt_builder() -> str:\n    return 'test prompt'", encoding="utf-8"
    )
    sp = await SystemPrompt.from_workspace(ws, "test")
    assert sp is not None

    result = await sp._builder()
    assert result == "test prompt"


@pytest.mark.anyio
async def test_syntax_error_in_system_py(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    systems = ws / "systems"
    await anyio.Path(systems).mkdir(parents=True)
    await anyio.Path(systems / "system.py").write_text("this is not valid python {{{", encoding="utf-8")
    sp = await SystemPrompt.from_workspace(ws, "test")
    assert await sp._builder() == ""


@pytest.mark.anyio
async def test_rebuild_checker_loads(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    systems = ws / "systems"
    await anyio.Path(systems).mkdir(parents=True)
    await anyio.Path(systems / "system.py").write_text(
        "async def system_prompt_builder() -> str:\n    return 'p'\n\n"
        "async def system_prompt_rebuild_checker() -> bool:\n    return True\n",
        encoding="utf-8",
    )
    sp = await SystemPrompt.from_workspace(ws, "test")
    assert sp is not None
    assert await sp._builder() == "p"
    assert await sp._checker() is True


@pytest.mark.anyio
async def test_first_ensure_refreshes_restored_system_prompt_once() -> None:
    calls: list[str] = []

    async def builder() -> str:
        calls.append("builder")
        return "fresh prompt"

    async def checker() -> bool:
        calls.append("checker")
        return False

    conversation = Conversation(
        messages=[
            {"role": "system", "content": "stale prompt"},
            {"role": "user", "content": "hello"},
        ]
    )
    prompt = SystemPrompt(builder=builder, checker=checker)

    await prompt.ensure(conversation)
    await prompt.ensure(conversation)

    assert calls == ["builder", "checker"]
    assert conversation.messages == [
        {"role": "system", "content": "fresh prompt"},
        {"role": "user", "content": "hello"},
    ]


@pytest.mark.anyio
async def test_failed_initial_build_retries_without_losing_history() -> None:
    calls = 0

    async def builder() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary failure")
        return "recovered prompt"

    conversation = Conversation(messages=[{"role": "user", "content": "keep me"}])
    prompt = SystemPrompt(builder=builder)

    await prompt.ensure(conversation)
    assert conversation.messages == [{"role": "user", "content": "keep me"}]

    await prompt.ensure(conversation)
    assert calls == 2
    assert conversation.messages == [
        {"role": "system", "content": "recovered prompt"},
        {"role": "user", "content": "keep me"},
    ]


@pytest.mark.anyio
async def test_workspace_without_builder_preserves_restored_history() -> None:
    conversation = Conversation(messages=[{"role": "user", "content": "existing"}])
    prompt = SystemPrompt()

    await prompt.ensure(conversation)

    assert conversation.messages == [{"role": "user", "content": "existing"}]


@pytest.mark.anyio
async def test_workspace_without_builder_keeps_empty_conversation_compatibility() -> None:
    conversation = Conversation()
    prompt = SystemPrompt()

    await prompt.ensure(conversation)

    assert conversation.messages == [{"role": "system", "content": ""}]


def test_replace_system_inserts_before_leading_user_message() -> None:
    conversation = Conversation(messages=[{"role": "user", "content": "keep me"}])

    conversation.replace_system("recovered prompt")

    assert conversation.messages == [
        {"role": "system", "content": "recovered prompt"},
        {"role": "user", "content": "keep me"},
    ]


def test_inserted_system_prompt_rolls_back_without_losing_history() -> None:
    conversation = Conversation(messages=[{"role": "user", "content": "keep me"}])

    conversation.replace_system("recovered prompt")
    conversation.rollback()

    assert conversation.messages == [{"role": "user", "content": "keep me"}]


def test_workspace_empty_string_uses_cwd(tmp_path: Path) -> None:
    session = Session(workspace="", channel_socket=str(tmp_path / "c.sock"), ai_socket=str(tmp_path / "a.sock"))
    assert session.workspace == ""


# ── Activation list parsing (--active-schedules / --deactive-schedules) ───────


def test_name_set_empty_by_default() -> None:
    """Nothing is activated by default - a schedule must be fired by exactly one Session."""
    assert Session._name_set("") == set()


def test_name_set_wildcard() -> None:
    assert Session._name_set(ACTIVATE_ALL) == {ACTIVATE_ALL}


def test_name_set_splits_and_trims() -> None:
    assert Session._name_set(" daily , weekly ,") == {"daily", "weekly"}


def test_name_set_wildcard_with_names() -> None:
    """Wildcard alongside names: is_active already covers all, so the names are redundant but harmless."""
    assert Session._name_set("*, daily") == {ACTIVATE_ALL, "daily"}
