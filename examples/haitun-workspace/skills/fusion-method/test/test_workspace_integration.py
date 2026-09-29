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


mtd_manage_tool = _load_module(
    "fusion_method_workspace_mtd_manage",
    _WORKSPACE_DIR / "tools" / "mtd_manage.py",
)
system_module = _load_module(
    "fusion_method_workspace_system",
    _WORKSPACE_DIR / "systems" / "system.py",
)


def test_workspace_exposes_one_python_fusion_method_runtime() -> None:
    skill_dir = _WORKSPACE_DIR / "skills" / "fusion-method"

    assert (skill_dir / "SKILL.md").is_file()
    assert (skill_dir / "grammar" / "FusionMethod.g4").is_file()
    assert (skill_dir / "fusion_method" / "method_runner.py").is_file()
    assert not (skill_dir / "fusion_method_next" / "__init__.py").exists()
    assert not (skill_dir / "fusion_method_next" / "method_runner.py").exists()
    assert (_WORKSPACE_DIR / "tools" / "run_mtd.py").is_file()


@pytest.mark.anyio
async def test_prompt_keeps_natural_language_ux_and_uses_python_runner(tmp_path: Path) -> None:
    workspace = anyio.Path(tmp_path)
    skill_dir = workspace / "skills" / "fusion-method"
    await skill_dir.mkdir(parents=True)
    await (skill_dir / "SKILL.md").write_text("---\nname: fusion-method\n---\n", encoding="utf-8")

    section = await system_module.System(workspace)._build_fusion_section()

    assert "natural language" in section
    assert "skills/fusion-method/SKILL.md" in section
    assert "run_mtd" in section
    assert ".method" in section
    assert "npx tsx" not in section
    assert "session_shim" not in section


@pytest.mark.anyio
async def test_mtd_manage_creates_and_promotes_method_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    source = "const demo: Method;\nmethod demo {}\n"

    created = await mtd_manage_tool.mtd_manage(
        action="create",
        target="adhoc",
        mtd_name="demo",
        mtd_source=source,
    )
    promoted = await mtd_manage_tool.mtd_manage(
        action="promote",
        mtd_name="demo",
        description="Demo mtd",
    )

    assert created == "Adhoc mtd created: 'demo'"
    assert promoted == "Mtd promoted to curated: 'demo'"
    adhoc = tmp_path / "mtds" / "adhoc" / "demo" / "mtd.method"
    curated = tmp_path / "mtds" / "curated" / "demo" / "MTD.md"
    assert adhoc.read_text(encoding="utf-8") == source
    curated_text = curated.read_text(encoding="utf-8")
    assert "```fusionmethod\n" + source.strip() + "\n```" in curated_text
    assert "source: mtds/adhoc/demo/mtd.method" in curated_text

    patched = await mtd_manage_tool.mtd_manage(
        action="patch",
        mtd_name="demo",
        description="Updated demo mtd",
        mtd_source=source.replace("demo {}", "demo { max_concurrency(demo) == 1; }"),
    )

    assert patched == "Curated mtd patched: 'demo'"
    assert "max_concurrency(demo) == 1" in curated.read_text(encoding="utf-8")
