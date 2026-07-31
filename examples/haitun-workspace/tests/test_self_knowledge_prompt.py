"""Identity, runtime-model, tool, and Skill self-knowledge contracts."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import anyio

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
SYSTEMS_DIR = WORKSPACE_ROOT / "systems"
if str(SYSTEMS_DIR) not in sys.path:
    sys.path.insert(0, str(SYSTEMS_DIR))

prompt_sections: Any = importlib.import_module("prompt_sections")
system: Any = importlib.import_module("system")


def test_underlying_model_is_not_the_agent_identity() -> None:
    line = prompt_sections.build_model_runtime_line("deepseek-v4-flash")

    assert line is not None
    assert "Underlying runtime model: deepseek-v4-flash" in line
    assert "not your agent identity" in line
    assert "questions about who you are or your name must still be answered with Haitun" in line
    assert "Current model identity" not in line


def test_runtime_does_not_claim_empty_capabilities() -> None:
    without_capabilities = prompt_sections.build_runtime_line(channel="web")
    with_capabilities = prompt_sections.build_runtime_line(
        channel="web",
        capabilities=["vision", "audio"],
    )

    assert "capabilities=" not in without_capabilities
    assert "channel_capabilities=vision,audio" in with_capabilities


def test_tools_and_skills_are_grounded_in_injected_runtime_facts() -> None:
    tooling = prompt_sections.build_tooling_section(["write", "read"])
    unavailable_index = prompt_sections.build_tooling_section(None)
    skills = prompt_sections.build_skills_section('<available_skills>\n  <skill name="example" />\n</available_skills>')

    assert "function/tool schemas attached to the current request are authoritative" in tooling
    assert "TOOLS.md is usage guidance, not availability" in tooling
    assert "static tool index could not be read" in unavailable_index
    assert "authoritative list of callable tools" in unavailable_index
    assert "On-demand Skill selection is the default behavior" in skills
    assert "local Skills are available now" in skills


async def test_prompt_keeps_core_when_optional_section_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    agent_root = anyio.Path(str(tmp_path / "agent"))
    user_workspace = anyio.Path(str(tmp_path / "user-workspace"))
    await agent_root.mkdir()
    await user_workspace.mkdir()

    async def fail_fusion(_self) -> str:
        raise RuntimeError("optional Fusion section failed")

    monkeypatch.setattr(system.System, "_build_fusion_section", fail_fusion)

    prompt = await system.System(
        agent_root,
        user_workspace=user_workspace,
    ).build_system_prompt(
        model="deepseek-v4-flash",
        tool_names=["read", "write"],
    )

    assert prompt.startswith(prompt_sections.IDENTITY_LINE)
    assert "## Self-Knowledge" in prompt
    assert "## Tooling" in prompt
    assert "- read:" in prompt
    assert "- write:" in prompt
    assert f"is: {await user_workspace.resolve()}" in prompt
    assert "Underlying runtime model: deepseek-v4-flash" in prompt
    assert prompt.index("## Self-Knowledge") < prompt.index(system.CACHE_BOUNDARY)
    assert prompt.index(system.CACHE_BOUNDARY) < prompt.index("Underlying runtime model:")


async def test_prompt_falls_back_when_tool_index_cannot_be_scanned(
    tmp_path: Path,
    monkeypatch,
) -> None:
    agent_root = anyio.Path(str(tmp_path / "agent"))
    await agent_root.mkdir()

    async def fail_tool_scan(_workspace) -> list[str]:
        raise OSError("unreadable tools directory")

    monkeypatch.setattr(system, "_scan_tool_names", fail_tool_scan)

    prompt = await system.System(agent_root).build_system_prompt()

    assert prompt.startswith(prompt_sections.IDENTITY_LINE)
    assert "The static tool index could not be read" in prompt
    assert "authoritative list of callable tools" in prompt


async def test_prompt_uses_fixed_identity_if_soul_loading_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    agent_root = anyio.Path(str(tmp_path / "agent"))
    await agent_root.mkdir()

    async def fail_identity(_workspace) -> str:
        raise OSError("SOUL.md unreadable")

    monkeypatch.setattr(system, "_load_soul_md", fail_identity)

    prompt = await system.System(agent_root).build_system_prompt(tool_names=[])

    assert prompt.startswith(prompt_sections.IDENTITY_LINE)
    assert "## Self-Knowledge" in prompt
    assert "No tools are available in this session." in prompt
