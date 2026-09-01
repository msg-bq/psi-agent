from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import anyio
import pytest

AGENT_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = AGENT_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

_read: Any = importlib.import_module("read")


def _bind_roots(monkeypatch: pytest.MonkeyPatch, workspace: Path, agent: Path) -> None:
    monkeypatch.setattr(
        _read._paths,
        "resolve_user_path",
        lambda path: anyio.Path(workspace) / path,
    )
    monkeypatch.setattr(
        _read._paths,
        "resolve_agent",
        lambda raw="": anyio.Path(agent),
    )


@pytest.mark.asyncio
async def test_read_skill_falls_back_to_agent_root_when_workspace_differs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    agent = tmp_path / "agent"
    skill = agent / "skills" / "workflow" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("workflow skill\n", encoding="utf-8")
    workspace.mkdir()
    _bind_roots(monkeypatch, workspace, agent)

    assert await _read.read("skills/workflow/SKILL.md") == "workflow skill\n"


@pytest.mark.asyncio
async def test_read_workspace_skill_shadows_agent_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    agent = tmp_path / "agent"
    workspace_skill = workspace / "skills" / "workflow" / "SKILL.md"
    agent_skill = agent / "skills" / "workflow" / "SKILL.md"
    workspace_skill.parent.mkdir(parents=True)
    agent_skill.parent.mkdir(parents=True)
    workspace_skill.write_text("workspace copy\n", encoding="utf-8")
    agent_skill.write_text("agent copy\n", encoding="utf-8")
    _bind_roots(monkeypatch, workspace, agent)

    assert await _read.read("skills/workflow/SKILL.md") == "workspace copy\n"


@pytest.mark.asyncio
async def test_read_non_skill_path_does_not_fall_back_to_agent_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    agent = tmp_path / "agent"
    workspace.mkdir()
    agent.mkdir()
    (agent / "TOOLS.md").write_text("agent-only\n", encoding="utf-8")
    _bind_roots(monkeypatch, workspace, agent)

    result = await _read.read("TOOLS.md")
    assert result.startswith("[Error] File not found:")
    assert str(workspace) in result
