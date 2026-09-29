"""Prompt contracts for the upper-layer FusionMethod method command."""

from __future__ import annotations

import ast
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


def _frontmatter_name(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        if line == "---":
            break
        if line.startswith("name:"):
            return line.partition(":")[2].strip()
    raise AssertionError(f"missing frontmatter name in {path}")


def _async_tool_parameters(filename: str, function_name: str) -> list[str]:
    tree = ast.parse((WORKSPACE_ROOT / "tools" / filename).read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == function_name)
    return [argument.arg for argument in function.args.args]


def test_method_command_does_not_add_a_management_tool():
    assert "method_manage" not in prompt_sections.CORE_TOOL_SUMMARIES
    assert "method_manage" not in prompt_sections.TOOL_ORDER
    assert not (WORKSPACE_ROOT / "tools" / "method_manage.py").exists()
    schema_names = {schema["function"]["name"] for schema in system._build_self_evolution_tool_schemas()}
    assert "method_manage" not in schema_names
    assert "method_manage" not in system._SELF_EVOLUTION_PROMPT


async def test_exact_method_command_precedes_natural_language_routing():
    section = await system.System(anyio.Path(str(WORKSPACE_ROOT)))._build_fusion_section()

    assert _async_tool_parameters("run_mtd.py", "run_mtd") == [
        "mtd_path",
        "inputs_json",
        "resource_capacities_json",
    ]
    command_index = section.index("### `/method:<slug>`")
    natural_language_index = section.index("### Natural-language activation")
    assert command_index < natural_language_index
    assert "matching exactly `/method:<slug>`" in section
    assert "Accept no suffix, inline parameters, or trailing" in section
    assert "argument syntax." in section
    assert "`mtds/methods/<slug>/<slug>.method`" in section
    inspect_index = section.index("Read that declaration before execution")
    collect_index = section.index("Resolve every required input from the conversation")
    call_index = section.index("call the existing `run_mtd` runner")
    assert inspect_index < collect_index < call_index
    assert "end the turn without calling `run_mtd`" in section
    assert "default empty input object" in section
    assert "exactly once for the initial execution, passing `mtd_path` and the complete" in section
    assert "Use an empty input object only when the declaration requires" in section
    assert "`$fusion_method/control`" in section
    assert "`run_mtd_resume` once with the matching `run_id`, `request_id`" in section
    assert "Repeat only when that resume returns another Human" in section
    assert "`runs/<run-id>/artifacts/` directory" in section
    assert "user-visible Artifact files are separate" in section
    assert "adds no operator or manifest protocol" in section
    assert "must not route through" in section
    assert "`mtd_manage`" in section
    assert "method_manage" not in section


async def test_registry_entries_are_not_injected_into_system_prompt(tmp_path: Path):
    workspace = anyio.Path(str(tmp_path))
    skill_dir = workspace / "skills" / "fusion-method"
    await skill_dir.mkdir(parents=True)
    await (skill_dir / "SKILL.md").write_text(
        "---\nname: mtd\ndescription: test\n---\n",
        encoding="utf-8",
    )

    registry_entry = workspace / "mtds" / "methods" / "private-method"
    await registry_entry.mkdir(parents=True)
    marker = "PRIVATE_METHOD_SOURCE_MUST_NOT_ENTER_STABLE_PROMPT"
    await (registry_entry / "private-method.method").write_text(
        f"method private_method {{ -- {marker}\n}}\n",
        encoding="utf-8",
    )

    section = await system.System(workspace)._build_fusion_section()
    assert marker not in section


def test_fusion_skill_defines_only_the_exact_frontend_command():
    skill = WORKSPACE_ROOT / "skills" / "fusion-method" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")

    assert _frontmatter_name(skill) == "fusion-method"
    assert "/method:<slug>" in text
    assert "/method:daily-brief" in text
    assert "accept a suffix or" in text
    assert "mtds/methods/<slug>/<slug>.method" in text
    assert "existing file tools" in text
    assert "new save/list/load operator" in text
    assert "method_manage" not in text
    assert "JSON object]" not in text
    assert "Step may save a self-contained child declaration" in text
    assert text.index("inspect `input_method(...)`") < text.index("invoke `run_mtd` exactly once")
    assert "end the turn without" in text
    assert "default empty input object" in text
    assert "Use an empty input object only when the declaration has no inputs." in text
    assert "resolve against the invoking psi workspace root" in text
