"""The workflow sample tool keeps the smallest useful local version history."""

from __future__ import annotations

import importlib.util
import inspect
import json
import sys
from pathlib import Path

import anyio
import pytest

from psi_agent.session.runtime_context import path_scope
from psi_agent.session.tool_registry import ToolFunction

REPO_ROOT = Path(__file__).resolve().parents[3]
TOOLS_DIR = REPO_ROOT / "agents" / "desktop" / "tools"


def _load_tool():
    path = TOOLS_DIR / "workflow_sample.py"
    spec = importlib.util.spec_from_file_location("workflow_sample_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    sys.path.insert(0, str(TOOLS_DIR))
    try:
        spec.loader.exec_module(module)
    finally:
        if sys.path[0] == str(TOOLS_DIR):
            sys.path.pop(0)
    return module


@pytest.mark.anyio
async def test_question_and_adjustment_save_exact_text_and_both_flow_versions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = anyio.Path(tmp_path / "workspace")
    flow_path = workspace / "flows" / "review.workflow"
    await flow_path.parent.mkdir(parents=True)
    await flow_path.write_text("workflow version one\n", encoding="utf-8")
    monkeypatch.setenv("PSI_APPDATA", str(tmp_path / "appdata"))
    tool = _load_tool()

    with path_scope(workspace=str(workspace), agent=str(REPO_ROOT / "agents" / "desktop")):
        initial_result = json.loads(
            await tool.workflow_sample_record(
                "flows/review.workflow",
                ["Run two reviews", "Combine their findings"],
                question="Review this repository.",
            )
        )
        await flow_path.write_text("workflow version two\n", encoding="utf-8")
        adjustment_result = json.loads(
            await tool.workflow_sample_record(
                "flows/review.workflow",
                ["Run three reviews", "Combine their findings"],
                adjustment="  Add a security reviewer.  ",
            )
        )

    initial = json.loads(await anyio.Path(initial_result["local_path"]).read_text(encoding="utf-8"))
    adjustment = json.loads(await anyio.Path(adjustment_result["local_path"]).read_text(encoding="utf-8"))

    assert initial["flow_key"] == adjustment["flow_key"]
    assert initial["question"] == "Review this repository."
    assert initial["adjustment"] is None
    assert adjustment["question"] is None
    assert adjustment["adjustment"] == "  Add a security reviewer.  "
    assert initial["flow"]["source"] == "workflow version one\n"
    assert adjustment["flow"]["source"] == "workflow version two\n"
    assert initial["flow"]["sha256"] != adjustment["flow"]["sha256"]
    assert initial["plan"] == ["Run two reviews", "Combine their findings"]
    assert str(tmp_path / "workspace") not in json.dumps(adjustment)


@pytest.mark.anyio
async def test_tool_rejects_ambiguous_text_and_empty_plan(tmp_path: Path) -> None:
    tool = _load_tool()

    with pytest.raises(ValueError, match="exactly one"):
        await tool.workflow_sample_record("flows/a.workflow", ["Plan"], question="Q", adjustment="A")
    with pytest.raises(ValueError, match="non-empty list"):
        await tool.workflow_sample_record("flows/a.workflow", [], question="Q")


def test_tool_exposes_one_documented_async_function_and_agent_copies_match() -> None:
    tool = _load_tool()
    public_async = {
        name for name in dir(tool) if not name.startswith("_") and inspect.iscoroutinefunction(getattr(tool, name))
    }
    assert public_async == {"workflow_sample_record"}

    fields = ToolFunction.from_callable(tool.workflow_sample_record).parameters["properties"]
    assert "Exact initial user request" in fields["question"]["description"]
    assert "Exact later user message" in fields["adjustment"]["description"]
    assert "private chain-of-thought" in fields["plan"]["description"]

    desktop = TOOLS_DIR / "workflow_sample.py"
    feishu = REPO_ROOT / "agents" / "feishu" / "tools" / "workflow_sample.py"
    assert desktop.read_bytes() == feishu.read_bytes()
