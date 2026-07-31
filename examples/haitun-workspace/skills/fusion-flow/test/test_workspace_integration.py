from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, cast

import anyio
import pytest

_WORKSPACE_DIR = Path(__file__).resolve().parents[3]


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    module_dir = str(path.parent)
    sys.path.insert(0, module_dir)
    try:
        spec.loader.exec_module(module)
    finally:
        if sys.path and sys.path[0] == module_dir:
            sys.path.pop(0)
    return cast(Any, module)


flow_manage_tool = _load_module(
    "fusion_flow_workspace_flow_manage",
    _WORKSPACE_DIR / "tools" / "flow_manage.py",
)
system_module = _load_module(
    "fusion_flow_workspace_system",
    _WORKSPACE_DIR / "systems" / "system.py",
)


def test_workspace_exposes_one_python_fusion_flow_runtime() -> None:
    skill_dir = _WORKSPACE_DIR / "skills" / "fusion-flow"

    assert (skill_dir / "SKILL.md").is_file()
    assert (skill_dir / "grammar" / "FusionFlow.g4").is_file()
    assert (skill_dir / "fusion_flow" / "workflow_runner.py").is_file()
    assert not (skill_dir / "fusion_flow_next" / "__init__.py").exists()
    assert not (skill_dir / "fusion_flow_next" / "workflow_runner.py").exists()
    assert (_WORKSPACE_DIR / "tools" / "run_flow.py").is_file()
    assert not (_WORKSPACE_DIR / "tools" / "flow_run.py").exists()


@pytest.mark.anyio
async def test_prompt_keeps_natural_language_ux_and_uses_python_runner(tmp_path: Path) -> None:
    workspace = anyio.Path(tmp_path)
    skill_dir = workspace / "skills" / "fusion-flow"
    await skill_dir.mkdir(parents=True)
    await (skill_dir / "SKILL.md").write_text("---\nname: flow\n---\n", encoding="utf-8")

    section = await system_module.System(workspace)._build_fusion_section()

    assert "natural language" in section
    assert "skills/fusion-flow/SKILL.md" in section
    assert "run_flow" in section
    assert ".workflow" in section
    assert "npx tsx" not in section
    assert "session_shim" not in section
    assert "flow_run(action=" not in section


@pytest.mark.anyio
async def test_flow_manage_creates_and_promotes_workflow_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    source = "const demo: Workflow;\nworkflow demo {}\n"

    created = await flow_manage_tool.flow_manage(
        action="create",
        target="adhoc",
        flow_name="demo",
        flow_source=source,
    )
    promoted = await flow_manage_tool.flow_manage(
        action="promote",
        flow_name="demo",
        description="Demo flow",
    )

    assert created == "Adhoc flow created: 'demo'"
    assert promoted == "Flow promoted to curated: 'demo'"
    adhoc = tmp_path / "flows" / "adhoc" / "demo" / "flow.workflow"
    curated = tmp_path / "flows" / "curated" / "demo" / "FLOW.md"
    assert adhoc.read_text(encoding="utf-8") == source
    curated_text = curated.read_text(encoding="utf-8")
    assert "```fusionflow\n" + source.strip() + "\n```" in curated_text
    assert "source: flows/adhoc/demo/flow.workflow" in curated_text

    patched = await flow_manage_tool.flow_manage(
        action="patch",
        flow_name="demo",
        description="Updated demo flow",
        flow_source=source.replace("demo {}", "demo { max_concurrency(demo) == 1; }"),
    )

    assert patched == "Curated flow patched: 'demo'"
    assert "max_concurrency(demo) == 1" in curated.read_text(encoding="utf-8")


@pytest.mark.anyio
async def test_flow_manage_discovers_g4_and_prefers_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    task_dir = tmp_path / "flows" / "review"
    task_dir.mkdir(parents=True)
    (task_dir / "review.g4").write_text("workflow from_g4 {}\n", encoding="utf-8")

    assert await flow_manage_tool.flow_manage(
        action="view",
        target="tasks",
        flow_name="review",
    ) == "workflow from_g4 {}\n"

    (task_dir / "review.workflow").write_text("workflow preferred {}\n", encoding="utf-8")

    assert await flow_manage_tool.flow_manage(
        action="view",
        target="tasks",
        flow_name="review",
    ) == "workflow preferred {}\n"
    assert "review: review.workflow" in await flow_manage_tool.flow_manage(action="list", target="tasks")


@pytest.mark.anyio
async def test_flow_manage_promotes_g4_adhoc_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    adhoc_dir = tmp_path / "flows" / "adhoc" / "g4-demo"
    adhoc_dir.mkdir(parents=True)
    source = "workflow g4_demo {}\n"
    (adhoc_dir / "flow.g4").write_text(source, encoding="utf-8")

    assert await flow_manage_tool.flow_manage(
        action="view",
        target="adhoc",
        flow_name="g4-demo",
    ) == source
    assert await flow_manage_tool.flow_manage(
        action="promote",
        flow_name="g4-demo",
    ) == "Flow promoted to curated: 'g4-demo'"

    curated = tmp_path / "flows" / "curated" / "g4-demo" / "FLOW.md"
    curated_text = curated.read_text(encoding="utf-8")
    assert "source: flows/adhoc/g4-demo/flow.g4" in curated_text
    assert "```fusionflow\n" + source.strip() + "\n```" in curated_text
