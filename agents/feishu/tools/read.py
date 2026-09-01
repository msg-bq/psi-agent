"""Read tool - read file contents."""

from __future__ import annotations

from pathlib import Path

import _runtime_paths as _paths


async def _resolve_read_path(file_path: str):
    """Resolve workspace files first, then bundled ``skills/`` from the agent root.

    The system prompt tells the model to read ``skills/<name>/SKILL.md`` with
    this tool.  Once agent capabilities and the user workspace are separate,
    that relative path no longer exists under the workspace even though the
    skill is bundled under the agent package.  Keep ordinary file IO
    workspace-relative, but make the documented ``skills/...`` lookup work.
    """
    workspace_path = _paths.resolve_user_path(file_path)
    if await workspace_path.exists():
        return workspace_path

    raw = Path((file_path or "").strip() or ".")
    if raw.is_absolute() or not raw.parts or raw.parts[0].lower() != "skills" or ".." in raw.parts:
        return workspace_path

    agent_path = _paths.resolve_agent() / str(raw)
    if await agent_path.exists():
        return agent_path
    return workspace_path


async def read(file_path: str, offset: int = 0, limit: int = 0) -> str:
    """Read file contents, optionally with line offset and limit.

    Relative paths normally resolve under the current Session workspace
    (``get_workspace()``).  When a missing relative path starts with
    ``skills/``, fall back to the current agent package so the system prompt's
    documented Skill lookup still works when ``agent != workspace``.  Existing
    workspace files always win. Absolute paths are used as-is.

    Args:
        file_path: Path to the file to read.
        offset: Line number to start reading from (0-indexed, 0 = beginning).
        limit: Maximum number of lines to read (0 = no limit).

    Returns:
        File contents as a string, or an error message if the file cannot be read.
    """
    path = await _resolve_read_path(file_path)
    if not await path.exists():
        return f"[Error] File not found: {path}"
    if not await path.is_file():
        return f"[Error] Not a file: {path}"

    content = await path.read_text(encoding="utf-8", errors="replace")

    if offset == 0 and limit == 0:
        return content

    lines = content.splitlines(keepends=True)
    selected = lines[offset:] if limit == 0 else lines[offset : offset + limit]
    return "".join(selected)
