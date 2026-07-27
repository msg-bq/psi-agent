from __future__ import annotations

import json
import sys
import types
from typing import Any

import anyio
import pytest

from psi_agent._workspace_tool_worker import WorkspaceToolWorker, is_standalone_executable


def test_standalone_executable_detects_source_pyinstaller_and_nuitka(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main_module = types.ModuleType("__main__")
    monkeypatch.setitem(sys.modules, "__main__", main_module)
    monkeypatch.delattr(sys, "frozen", raising=False)

    assert is_standalone_executable() is False

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert is_standalone_executable() is True

    monkeypatch.delattr(sys, "frozen")
    vars(main_module)["__compiled__"] = object()
    assert is_standalone_executable() is True


@pytest.mark.anyio
async def test_workspace_tool_worker_loads_and_runs_private_worker(tmp_path: Any) -> None:
    tool_path = anyio.Path(str(tmp_path / "tool.py"))
    state_path = anyio.Path(str(tmp_path / "state.txt"))
    await tool_path.write_text(
        "\n".join(
            (
                "import anyio",
                "",
                "async def _worker(state_path: anyio.Path) -> None:",
                "    value = await state_path.read_text(encoding='utf-8')",
                "    await (state_path.parent / 'done.txt').write_text(value, encoding='utf-8')",
                "",
            )
        ),
        encoding="utf-8",
    )
    await state_path.write_text("finished", encoding="utf-8")

    await WorkspaceToolWorker(str(tool_path), str(state_path)).run()

    assert await (state_path.parent / "done.txt").read_text(encoding="utf-8") == "finished"


@pytest.mark.anyio
async def test_workspace_tool_worker_requires_private_async_entrypoint(tmp_path: Any) -> None:
    tool_path = anyio.Path(str(tmp_path / "tool.py"))
    state_path = anyio.Path(str(tmp_path / "state.txt"))
    await tool_path.write_text("VALUE = 1\n", encoding="utf-8")

    with pytest.raises(TypeError, match="no async _worker"):
        await WorkspaceToolWorker(str(tool_path), str(state_path)).run()


@pytest.mark.parametrize(
    ("owner_token", "lock_exists"),
    [("bootstrap-token", False), ("replacement-token", True)],
)
@pytest.mark.anyio
async def test_workspace_tool_worker_releases_only_its_bootstrap_lock(
    tmp_path: Any,
    owner_token: str,
    lock_exists: bool,
) -> None:
    root = anyio.Path(str(tmp_path))
    tool_path = root / "broken_tool.py"
    state_path = root / "state.json"
    lock_dir = root / "run.lock"
    await tool_path.write_text("def broken(:\n", encoding="utf-8")
    await lock_dir.mkdir()
    await (lock_dir / "owner.json").write_text(
        json.dumps({"run_token": owner_token}),
        encoding="utf-8",
    )
    await state_path.write_text(
        json.dumps(
            {
                "run_token": "bootstrap-token",
                "lock_dir": str(lock_dir),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SyntaxError):
        await WorkspaceToolWorker(str(tool_path), str(state_path)).run()

    assert await lock_dir.exists() is lock_exists
    if lock_exists:
        assert json.loads(await (lock_dir / "owner.json").read_text(encoding="utf-8")) == {
            "run_token": "replacement-token"
        }
