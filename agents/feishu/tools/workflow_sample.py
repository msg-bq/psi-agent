"""Save small, local question/flow records for workflow authoring."""

from __future__ import annotations

import hashlib
import json
import secrets
import sys
from datetime import UTC, datetime
from pathlib import Path

import anyio

from psi_agent._appdata import resolve_appdata_root as _resolve_appdata_root

_TOOLS_DIR = Path(__file__).parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

_paths = __import__("_runtime_paths")


async def _resolve_flow(flow_path: str) -> tuple[anyio.Path, str]:
    workspace = await anyio.Path(_paths.workspace_dir()).resolve()
    candidate = anyio.Path(flow_path)
    if candidate.is_absolute():
        raise ValueError("flow_path must be relative to the workspace")
    resolved = await (workspace / flow_path).resolve()
    flows_dir = await (workspace / "flows").resolve()
    if not Path(str(resolved)).is_relative_to(Path(str(flows_dir))):
        raise ValueError("flow_path must stay inside the workspace flows directory")
    if resolved.suffix.lower() not in {".workflow", ".g4"} or not await resolved.is_file():
        raise ValueError("flow_path must name an existing .workflow or .g4 file")
    relative = Path(str(resolved)).relative_to(Path(str(workspace))).as_posix()
    return resolved, relative


async def workflow_sample_record(
    flow_path: str,
    plan: list[str],
    question: str = "",
    adjustment: str = "",
) -> str:
    """Save one local authoring snapshot; no data is uploaded.

    Exactly one of ``question`` and ``adjustment`` must be provided. Call with
    ``question`` after first authoring a flow, and with the user's exact
    ``adjustment`` wording after any later requested change, including a
    request that ultimately leaves the flow unchanged.

    Args:
        flow_path: Workspace-relative path under ``flows/``. The current full
            UTF-8 source is copied into the record, so later edits do not erase
            this version.
        plan: Short ordered planning outline for this version. Store observable
            design steps only, never private chain-of-thought.
        question: Exact initial user request. Leave empty for an adjustment.
        adjustment: Exact later user message asking to change or retain the
            flow. Leave empty for the initial request.

    Returns:
        JSON with ``event_id``, stable ``flow_key``, and ``local_path``. Events
        with the same ``flow_key`` are ordered by ``created_at``; each new
        question starts a lineage and following adjustments belong to it.
    """

    has_question = bool(question.strip())
    has_adjustment = bool(adjustment.strip())
    if has_question == has_adjustment:
        raise ValueError("provide exactly one of question or adjustment")
    normalized_plan = [item.strip() for item in plan if isinstance(item, str) and item.strip()]
    if len(normalized_plan) != len(plan) or not normalized_plan:
        raise ValueError("plan must be a non-empty list of non-empty strings")

    resolved, relative_path = await _resolve_flow(flow_path)
    source = await resolved.read_text(encoding="utf-8")
    workspace = str(await anyio.Path(_paths.workspace_dir()).resolve())
    flow_key = hashlib.sha256(f"{workspace}\0{relative_path}".encode()).hexdigest()
    event_id = secrets.token_hex(16)
    event = {
        "schema_version": 1,
        "event_id": event_id,
        "flow_key": flow_key,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "question": question if has_question else None,
        "adjustment": adjustment if has_adjustment else None,
        "plan": normalized_plan,
        "flow": {
            "path": relative_path,
            "source": source,
            "sha256": hashlib.sha256(source.encode()).hexdigest(),
        },
    }

    # ponytail: immutable event files avoid a lock and index. Add an index only
    # if measured export scans become slow.
    event_dir = anyio.Path(await _resolve_appdata_root()) / "workflow-samples" / flow_key
    await event_dir.mkdir(parents=True, exist_ok=True)
    target = event_dir / f"{event_id}.json"
    temporary = event_dir / f".{event_id}.tmp"
    await temporary.write_text(
        json.dumps(event, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    await temporary.replace(target)
    return json.dumps(
        {
            "ok": True,
            "event_id": event_id,
            "flow_key": flow_key,
            "local_path": str(target),
        },
        ensure_ascii=False,
    )
