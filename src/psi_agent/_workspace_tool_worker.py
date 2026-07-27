"""Run one private workspace-tool worker in a standalone psi-agent process."""

from __future__ import annotations

import hashlib
import inspect
import json
import sys
import types
from contextlib import suppress
from dataclasses import dataclass
from typing import Annotated, Any

import anyio
from tyro import conf

from psi_agent._logging import setup_logging


async def _read_state(path: anyio.Path) -> dict[str, object] | None:
    try:
        value = json.loads(await path.read_text(encoding="utf-8"))
    except OSError, UnicodeError, json.JSONDecodeError:
        return None
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        return None
    return value


async def _release_bootstrap_lock(state: dict[str, object]) -> None:
    lock_value = state.get("lock_dir")
    token = state.get("run_token")
    if not isinstance(lock_value, str) or not lock_value or not isinstance(token, str) or not token:
        return
    lock_dir = anyio.Path(lock_value)
    if await lock_dir.is_symlink() or not await lock_dir.is_dir():
        return
    owner_path = lock_dir / "owner.json"
    if await owner_path.is_symlink():
        return
    owner = await _read_state(owner_path)
    if owner is None or owner.get("run_token") != token:
        return
    with suppress(FileNotFoundError, OSError):
        await owner_path.unlink()
        await lock_dir.rmdir()


async def _cleanup_bootstrap_failure(state_path: anyio.Path) -> None:
    state = await _read_state(state_path)
    if state is None:
        return
    with suppress(OSError):
        await _release_bootstrap_lock(state)


def is_standalone_executable() -> bool:
    """Return whether this process is a PyInstaller or Nuitka executable."""

    main_module = sys.modules.get("__main__")
    return bool(
        vars(sys).get("frozen", False)
        or (main_module is not None and vars(main_module).get("__compiled__") is not None)
    )


@dataclass
class WorkspaceToolWorker:
    """Internal subprocess entry point for long-running workspace tools."""

    tool_path: Annotated[str, conf.Positional]
    state_path: Annotated[str, conf.Positional]

    async def run(self) -> None:
        setup_logging(verbose=False)

        module_name: str | None = None
        try:
            tool_path = anyio.Path(self.tool_path)
            if not await tool_path.is_file():
                raise FileNotFoundError(f"workspace tool not found: {tool_path}")
            source = await tool_path.read_text(encoding="utf-8")
            digest = hashlib.sha256(source.encode()).hexdigest()
            module_name = f"psi_workspace_worker_{tool_path.stem}_{digest}"
            module = types.ModuleType(module_name)
            module.__file__ = str(tool_path)
            sys.modules[module_name] = module
            exec(compile(source, str(tool_path), "exec"), module.__dict__)
            worker: Any = getattr(module, "_worker", None)
            if not inspect.iscoroutinefunction(worker):
                raise TypeError(f"workspace tool has no async _worker(): {tool_path}")
        except BaseException:
            if module_name is not None:
                sys.modules.pop(module_name, None)
            with anyio.CancelScope(shield=True):
                await _cleanup_bootstrap_failure(anyio.Path(self.state_path))
            raise

        assert module_name is not None
        try:
            await worker(anyio.Path(self.state_path))
        finally:
            sys.modules.pop(module_name, None)
