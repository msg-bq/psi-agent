"""Run a FusionFlow Next G4 workflow in the background.

This tool is intentionally separate from ``flow_run``.  ``flow_run`` remains
the legacy TypeScript ``.flow.ts`` runner; ``run_flow`` owns the G4 pipeline:

    G4 source -> Core IR -> WorkflowGraph -> ExecutionPlan -> Agent Sessions

The public protocol stays long-running friendly:

    start  -> validate synchronously, launch a detached worker, return a token
    status -> wait for the next completed node, terminal state, or keepalive
    result -> return the final outputs and persisted run artifacts

The initial executable subset is one-shot Agent DAGs.  Program and Human
executors, residual assertions, foreach, resources, retries, and cycles fail
during ``start`` rather than being silently approximated.
"""

from __future__ import annotations

import ctypes
import importlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from contextlib import aclosing, suppress
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, cast

import aiohttp
import anyio

from psi_agent._sockets import resolve_connector_and_endpoint
from psi_agent.channel._core import ChannelCore
from psi_agent.channel._types import TextChunk
from psi_agent.session import Session
from psi_agent.workflow_execution import (
    Await,
    ExecutionPlan,
    Invoke,
    StepDispatcher,
    generate_plan,
)
from psi_agent.workflow_execution import execute_plan as _execute_plan
from psi_agent.workflow_graph import ProducesEdge, StepNode

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
_WORKSPACE_DIR = os.path.dirname(_TOOLS_DIR)


def _resolve_skill_dir() -> str:
    skills_dir = os.path.join(_WORKSPACE_DIR, "skills")
    candidates = (
        os.path.join(skills_dir, "fusion-flow-next"),
        os.path.join(skills_dir, "fusion-flow"),
    )
    for candidate in candidates:
        if os.path.isfile(os.path.join(candidate, "examples", "run_workflow.py")) and os.path.isdir(
            os.path.join(candidate, "fusion_flow_next")
        ):
            return candidate
    raise RuntimeError("FusionFlow G4 runtime not found; expected fusion-flow-next or its fusion-flow replacement")


_SKILL_DIR = _resolve_skill_dir()
_THIS_FILE = os.path.abspath(__file__)
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)

_RUN_WORKFLOW_MODULE = importlib.import_module("examples.run_workflow")
_EXECUTION_MODULE = importlib.import_module("fusion_flow_next.execution")

type CompiledWorkflow = Any
type StepCompletion = Callable[
    [StepNode, tuple[str, ...], Mapping[str, object]],
    Awaitable[str],
]

_compile_workflow = cast(Callable[[str], CompiledWorkflow], _RUN_WORKFLOW_MODULE.compile_workflow)
_AgentConfig = cast(Any, _EXECUTION_MODULE.AgentConfig)
_SessionResult = cast(Any, _EXECUTION_MODULE.SessionResult)
_assert_safe_name = cast(Callable[[str], str], _EXECUTION_MODULE.assert_safe_name)
_flow = cast(Any, _EXECUTION_MODULE.flow)
_run_execution = cast(Any, _EXECUTION_MODULE.run)

_TOKEN_PREFIX = "g4-"
_TOKEN_LENGTH = len(_TOKEN_PREFIX) + 32
_ATTEMPT_ID_LENGTH = 32
_STILL_ACTIVE = 259
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_RUN_LOCKS_DIRECTORY = ".run-flow-next-locks"
_RUN_MARKER_NAME = "run-flow-next.json"
_RUN_MARKER_KIND = "psi-agent/fusion-flow-next"
_RUN_MARKER_VERSION = 1
_STEP_CACHE_VERSION = 2
_META_ATTEMPT_ID = "run_flow_attempt_id"
_META_TOKEN_DIGEST = "run_flow_token_sha256"
_PROMPT_ROOT_FILES = frozenset(
    {
        ".cursorrules",
        "agents.md",
        "bootstrap.md",
        "claude.md",
        "heartbeat.md",
        "identity.md",
        "session.md",
        "soul.md",
        "tools.md",
        "user.md",
    }
)
_CACHE_ENVIRONMENT = (
    "FLOW_NEXT_CACHE_IDENTITY",
    "FLOW_PSI_AI",
    "FLOW_PSI_BASE_URL",
    "FLOW_PSI_MODEL",
    "HAITUN_AGENT_ID",
    "HAITUN_CHANNEL",
    "HAITUN_KNOWLEDGE_CUTOFF",
    "HAITUN_MODEL",
    "HAITUN_TIMEZONE",
    "PSI_AI_BASE_URL",
    "PSI_AI_MODEL",
    "PSI_AI_PROVIDER",
    "SHELL",
)
_KERNEL32: Any | None = None

if sys.platform == "win32":
    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _KERNEL32.OpenProcess.argtypes = (
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_uint32,
    )
    _KERNEL32.OpenProcess.restype = ctypes.c_void_p
    _KERNEL32.GetExitCodeProcess.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_ulong),
    )
    _KERNEL32.GetExitCodeProcess.restype = ctypes.c_int
    _KERNEL32.CloseHandle.argtypes = (ctypes.c_void_p,)
    _KERNEL32.CloseHandle.restype = ctypes.c_int


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _make_run_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def _make_run_token() -> str:
    return f"{_TOKEN_PREFIX}{uuid.uuid4().hex}"


def _make_attempt_id() -> str:
    return uuid.uuid4().hex


def _validate_run_token(token: str) -> str:
    if len(token) != _TOKEN_LENGTH or not token.startswith(_TOKEN_PREFIX):
        raise ValueError("invalid run_token")
    suffix = token.removeprefix(_TOKEN_PREFIX)
    if any(character not in "0123456789abcdef" for character in suffix):
        raise ValueError("invalid run_token")
    return token


def _validate_attempt_id(attempt_id: str) -> str:
    if len(attempt_id) != _ATTEMPT_ID_LENGTH:
        raise ValueError("invalid attempt_id")
    if any(character not in "0123456789abcdef" for character in attempt_id):
        raise ValueError("invalid attempt_id")
    return attempt_id


def _run_token_digest(token: str) -> str:
    return sha256(_validate_run_token(token).encode()).hexdigest()


def _state_dir() -> anyio.Path:
    configured = os.environ.get("FLOW_NEXT_RUN_STATE_DIR", "").strip()
    if configured:
        expanded = os.path.expandvars(os.path.expanduser(configured))
        return anyio.Path(os.path.abspath(expanded))
    return anyio.Path(str(_WORKSPACE_DIR)) / ".psi" / "run-flow-next"


def _state_path(token: str) -> anyio.Path:
    return _state_dir() / f"{_validate_run_token(token)}.json"


def _terminal_path(token: str) -> anyio.Path:
    return _state_dir() / f"{_validate_run_token(token)}.result.json"


async def _atomic_write_text(path: anyio.Path, content: str) -> None:
    await path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        await temporary.write_text(content, encoding="utf-8")
        await temporary.replace(path)
    finally:
        with anyio.CancelScope(shield=True):
            try:
                if await temporary.exists():
                    await temporary.unlink()
            except OSError:
                pass


async def _atomic_write_json(path: anyio.Path, value: Mapping[str, object]) -> None:
    await _atomic_write_text(
        path,
        f"{json.dumps(dict(value), ensure_ascii=False, indent=2, sort_keys=True)}\n",
    )


async def _read_json_object(path: anyio.Path) -> dict[str, object] | None:
    try:
        raw = await path.read_text(encoding="utf-8")
        value = json.loads(raw)
    except FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError:
        return None
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        return None
    return cast(dict[str, object], value)


async def _release_run_lock(
    lock_dir: anyio.Path,
    *,
    expected_token: str,
) -> bool:
    if await lock_dir.is_symlink() or not await lock_dir.is_dir():
        return False
    owner_path = lock_dir / "owner.json"
    owner = await _read_json_object(owner_path)
    if owner is None or owner.get("run_token") != expected_token:
        return False
    try:
        await owner_path.unlink()
        await lock_dir.rmdir()
    except FileNotFoundError, OSError:
        return False
    return True


def _run_lock_path(runs_dir: str, run_id: str) -> anyio.Path:
    canonical_root = os.path.normcase(os.path.realpath(os.path.abspath(runs_dir)))
    namespace = sha256(os.fsencode(canonical_root)).hexdigest()[:24]
    return anyio.Path(canonical_root).parent / _RUN_LOCKS_DIRECTORY / namespace / run_id


async def _acquire_run_lock(runs_dir: str, run_id: str, run_token: str) -> anyio.Path:
    lock_dir = _run_lock_path(runs_dir, run_id)
    lock_root = lock_dir.parent.parent
    await lock_root.mkdir(exist_ok=True)
    if await lock_root.is_symlink() or not await lock_root.is_dir():
        raise ValueError(f"run lock root must be a real directory: {lock_root}")
    await lock_dir.parent.mkdir(exist_ok=True)
    if await lock_dir.parent.is_symlink() or not await lock_dir.parent.is_dir():
        raise ValueError(f"run lock namespace must be a real directory: {lock_dir.parent}")
    try:
        await lock_dir.mkdir()
    except FileExistsError as error:
        if await lock_dir.is_symlink():
            detail = "unsafe symbolic link"
        else:
            owner = await _read_json_object(lock_dir / "owner.json")
            pid_value = owner.get("pid", 0) if owner is not None else 0
            pid = pid_value if isinstance(pid_value, int) else 0
            if pid > 0:
                detail = f"{'active' if _pid_alive(pid) else 'stale'} owner pid {pid}"
            else:
                detail = "owner is starting or stale"
        raise RuntimeError(
            f"run {run_id!r} is already locked ({detail}); inspect and remove a stale lock manually: {lock_dir}"
        ) from error

    try:
        await _atomic_write_json(
            lock_dir / "owner.json",
            {
                "run_token": run_token,
                "run_id": run_id,
                "runs_dir": runs_dir,
                "pid": 0,
                "started_ts": time.time(),
            },
        )
    except BaseException:
        with anyio.CancelScope(shield=True):
            with suppress(OSError):
                await lock_dir.rmdir()
        raise
    return lock_dir


async def _set_run_lock_pid(lock_dir: anyio.Path, run_token: str, pid: int) -> None:
    if await lock_dir.is_symlink():
        raise RuntimeError("run lock was replaced by a symbolic link")
    owner_path = lock_dir / "owner.json"
    owner = await _read_json_object(owner_path)
    if owner is None or owner.get("run_token") != run_token:
        raise RuntimeError("run lock ownership changed before worker startup")
    owner["pid"] = pid
    await _atomic_write_json(owner_path, owner)


def _resolve_path(raw: str, *, base: str) -> anyio.Path:
    expanded = os.path.expandvars(os.path.expanduser(raw.strip()))
    if not os.path.isabs(expanded):
        expanded = os.path.join(base, expanded)
    return anyio.Path(os.path.abspath(expanded))


def _absolute_path(raw: str) -> str:
    return os.path.abspath(raw)


async def _prepare_runs_dir(work_dir: str) -> str:
    work_path = anyio.Path(work_dir)
    if not await work_path.is_dir():
        raise NotADirectoryError(f"workflow working directory does not exist: {work_path}")
    resolved_work = await work_path.resolve()
    runs_path = resolved_work / "runs"
    await runs_path.mkdir(exist_ok=True)
    if await runs_path.is_symlink():
        raise ValueError(f"runs directory must not be a symbolic link: {runs_path}")
    if not await runs_path.is_dir():
        raise NotADirectoryError(f"runs path is not a directory: {runs_path}")
    resolved_runs = await runs_path.resolve()
    if resolved_runs.parent != resolved_work:
        raise ValueError(f"runs directory escapes the working directory: {runs_path}")
    return str(resolved_runs)


async def _resolve_run_dir(runs_dir: str, run_id: str, *, resume: bool) -> str:
    root = anyio.Path(runs_dir)
    candidate = root / run_id
    if await candidate.is_symlink():
        raise ValueError(f"run directory must not be a symbolic link: {candidate}")
    if resume:
        if not await candidate.is_dir():
            raise FileNotFoundError(f"resume run does not exist: {candidate}")
        resolved = await candidate.resolve()
        if resolved.parent != await root.resolve():
            raise ValueError(f"resume run escapes the runs directory: {candidate}")
        return str(resolved)
    if await candidate.exists():
        raise FileExistsError(f"run directory already exists: {candidate}")
    return str(candidate)


async def _validate_resume_provenance(
    run_dir: str,
    run_id: str,
    workflow_id: str,
) -> None:
    run_path = anyio.Path(run_dir)
    marker_path = run_path / _RUN_MARKER_NAME
    if await marker_path.is_symlink() or not await marker_path.is_file():
        raise ValueError(f"resume run {run_id!r} was not created by FusionFlow Next run_flow")
    resolved_marker = await marker_path.resolve()
    if resolved_marker.parent != run_path:
        raise ValueError(f"resume marker escapes the run directory: {marker_path}")
    marker = await _read_json_object(resolved_marker)
    if (
        marker is None
        or marker.get("runner") != _RUN_MARKER_KIND
        or marker.get("version") != _RUN_MARKER_VERSION
        or marker.get("run_id") != run_id
        or marker.get("workflow_id") != workflow_id
    ):
        raise ValueError(f"resume run {run_id!r} has invalid FusionFlow Next run_flow provenance")


async def _load_inputs(
    *,
    inputs_json: str,
    inputs_path: str,
    base: str,
) -> dict[str, object]:
    if inputs_json.strip() and inputs_path.strip():
        raise ValueError("inputs_json and inputs_path are mutually exclusive")
    raw = inputs_json
    if inputs_path.strip():
        path = _resolve_path(inputs_path, base=base)
        raw = await path.read_text(encoding="utf-8")
    if not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"workflow inputs must be a JSON object: {error.msg}") from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("workflow inputs must be a JSON object with string keys")
    return cast(dict[str, object], value)


def _preflight(
    source: str,
    inputs: Mapping[str, object],
) -> tuple[CompiledWorkflow, ExecutionPlan]:
    compiled = _compile_workflow(source)
    graph = compiled.graph
    expected_inputs = {artifact.artifact_id for artifact in graph.artifacts if artifact.is_input}
    supplied_inputs = set(inputs)
    if supplied_inputs != expected_inputs:
        raise ValueError(
            f"workflow inputs must match exactly: expected {sorted(expected_inputs)}, got {sorted(supplied_inputs)}"
        )

    for artifact in graph.artifacts:
        try:
            _assert_safe_name(artifact.artifact_id)
        except ValueError as error:
            raise ValueError(f"Artifact ID {artifact.artifact_id!r} is not runtime-safe: {error}") from error

    for step in graph.steps:
        try:
            _assert_safe_name(step.step_id)
        except ValueError as error:
            raise ValueError(f"Step ID {step.step_id!r} is not runtime-safe: {error}") from error
        kind = compiled.executor_kinds[step.executor_id]
        if kind != "Agent":
            raise ValueError(f"{kind} executor {step.executor_id!r} is not supported by run_flow")
        if step.instruction_id is None:
            raise ValueError(f"Agent step {step.step_id!r} has no step_instruction")

    return compiled, generate_plan(graph)


def _normalize_step_output(
    step_id: str,
    output_ids: tuple[str, ...],
    text: str,
) -> dict[str, object]:
    """Turn one Agent reply into the exact outputs required by a graph step."""

    stripped = text.strip()
    if not output_ids:
        if not stripped:
            return {}
        try:
            parsed_empty = json.loads(stripped)
        except json.JSONDecodeError as error:
            raise ValueError(f"step {step_id!r} produces no artifacts") from error
        if parsed_empty == {}:
            return {}
        raise ValueError(f"step {step_id!r} produces no artifacts")

    if len(output_ids) == 1:
        output_id = output_ids[0]
        try:
            parsed_single = json.loads(stripped)
        except json.JSONDecodeError:
            return {output_id: text}
        if isinstance(parsed_single, dict) and set(parsed_single) == {output_id}:
            return {output_id: parsed_single[output_id]}
        return {output_id: parsed_single}

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as error:
        raise ValueError(f"step {step_id!r} must return a JSON object for multiple artifacts") from error
    if not isinstance(parsed, dict) or not all(isinstance(key, str) for key in parsed):
        raise ValueError(f"step {step_id!r} must return a JSON object for multiple artifacts")
    expected = set(output_ids)
    actual = set(parsed)
    if actual != expected:
        raise ValueError(
            f"outputs for {step_id!r} must match exactly: expected {sorted(expected)}, got {sorted(actual)}"
        )
    return cast(dict[str, object], parsed)


def _binding_text(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str)


def _context_text(value: object) -> str:
    """Encode a typed artifact without collapsing strings into scalar values."""

    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _context_value(value: str) -> object:
    """Decode the canonical JSON representation passed through flow.session."""

    return json.loads(value)


async def _prepare_instruction(
    instruction_id: str,
    *,
    work_dir: str,
) -> str:
    reference = instruction_id.strip()
    candidate = _resolve_path(reference, base=work_dir)
    work_root = await anyio.Path(work_dir).resolve()
    identity: dict[str, object] = {
        "reference": reference,
        "kind": "reference",
        "work_dir_sha256": sha256(str(work_root).encode()).hexdigest(),
    }
    try:
        resolved = await candidate.resolve()
        path_exists = await candidate.exists() or await candidate.is_symlink()
    except OSError:
        identity["kind"] = "unreadable"
        path_exists = False
        resolved = candidate
    if path_exists and resolved != work_root and work_root not in resolved.parents:
        raise ValueError(f"instruction path escapes the workflow working directory: {reference!r}")
    if path_exists and not await resolved.is_file():
        raise ValueError(f"instruction path is not a regular file: {reference!r}")
    if path_exists:
        try:
            content_bytes = await resolved.read_bytes()
        except OSError as error:
            raise RuntimeError(f"instruction file cannot be read: {reference!r}") from error
        else:
            identity["kind"] = "file"
            identity["path"] = resolved.relative_to(work_root).as_posix()
            identity["sha256"] = sha256(content_bytes).hexdigest()
    return json.dumps(identity, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


async def _add_cache_files(
    manifest: dict[str, str],
    *,
    root: anyio.Path,
    pattern: str,
    prefix: str,
) -> None:
    try:
        paths = [path async for path in root.glob(pattern)]
    except OSError:
        return
    for path in sorted(paths, key=str):
        try:
            if not await path.is_file():
                continue
            digest = sha256(await path.read_bytes()).hexdigest()
        except OSError:
            digest = "unreadable"
        relative = path.relative_to(root).as_posix()
        manifest[f"{prefix}{relative}"] = digest


async def _ai_socket_cache_identity(ai_socket: str) -> dict[str, str]:
    identity = {"address_sha256": sha256(ai_socket.encode()).hexdigest()}
    if ai_socket.startswith(("http://", "https://", "\\\\.\\pipe\\")):
        return identity
    try:
        socket_stat = await anyio.Path(ai_socket).stat()
    except OSError:
        return identity
    instance = f"{socket_stat.st_dev}:{socket_stat.st_ino}:{socket_stat.st_ctime_ns}"
    identity["instance_sha256"] = sha256(instance.encode()).hexdigest()
    return identity


async def _workspace_cache_identity(
    workspace: str,
    ai_socket: str,
) -> str:
    root = await anyio.Path(workspace).resolve()
    files: dict[str, str] = {}
    try:
        root_entries = [entry async for entry in root.iterdir()]
    except OSError:
        root_entries = []
    for entry in sorted(root_entries, key=lambda item: item.name.lower()):
        if entry.name.lower() not in _PROMPT_ROOT_FILES:
            continue
        try:
            if await entry.is_file():
                files[entry.name] = sha256(await entry.read_bytes()).hexdigest()
        except OSError:
            files[entry.name] = "unreadable"

    for pattern in ("systems/*.py", "tools/*.py", "skills/*/SKILL.md", "flows/*/*.flow.ts"):
        await _add_cache_files(files, root=root, pattern=pattern, prefix="")
    await _add_cache_files(
        files,
        root=root,
        pattern="flows/curated/*/FLOW.md",
        prefix="",
    )

    global_agent_root = await anyio.Path("~/.agent").expanduser()
    await _add_cache_files(
        files,
        root=global_agent_root,
        pattern="AGENTS.md",
        prefix="~/.agent/",
    )
    await _add_cache_files(
        files,
        root=global_agent_root,
        pattern="agents.md",
        prefix="~/.agent/",
    )
    await _add_cache_files(
        files,
        root=global_agent_root,
        pattern="skills/*/SKILL.md",
        prefix="~/.agent/",
    )

    environment = {name: sha256(os.environ.get(name, "").encode()).hexdigest() for name in _CACHE_ENVIRONMENT}
    try:
        runner_digest = sha256(await anyio.Path(_THIS_FILE).read_bytes()).hexdigest()
    except OSError:
        runner_digest = f"version:{_STEP_CACHE_VERSION}"
    return json.dumps(
        {
            "ai": await _ai_socket_cache_identity(ai_socket),
            "environment": environment,
            "files": files,
            "runner_sha256": runner_digest,
            "workspace_sha256": sha256(str(root).encode()).hexdigest(),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _flatten_execution_error(error: ExceptionGroup) -> Exception:
    leaves: list[Exception] = []

    def visit(current: Exception) -> None:
        if isinstance(current, ExceptionGroup):
            for nested in current.exceptions:
                visit(nested)
        else:
            leaves.append(current)

    visit(error)
    if len(leaves) == 1:
        return leaves[0]
    details = "; ".join(f"{item.__class__.__name__}: {item}" for item in leaves)
    return RuntimeError(f"multiple workflow step failures: {details}")


def _outputs_by_step(compiled: CompiledWorkflow) -> dict[str, tuple[str, ...]]:
    values: dict[str, list[str]] = {step.step_id: [] for step in compiled.graph.steps}
    for edge in compiled.graph.edges:
        if isinstance(edge, ProducesEdge):
            values[edge.step_id].append(edge.artifact_id)
    return {step_id: tuple(sorted(output_ids)) for step_id, output_ids in values.items()}


def _plan_payload(plan: ExecutionPlan) -> dict[str, object]:
    fibers: list[dict[str, object]] = []
    for fiber in plan.fibers:
        instructions: list[dict[str, object]] = []
        for instruction in fiber.instructions:
            if isinstance(instruction, Await):
                instructions.append({"kind": "await", "step_ids": list(instruction.step_ids)})
            elif isinstance(instruction, Invoke):
                instructions.append({"kind": "invoke", "step_id": instruction.step_id})
        fibers.append({"fiber_id": fiber.fiber_id, "instructions": instructions})
    return {
        "workflow_id": plan.workflow_id,
        "fibers": fibers,
    }


def _allocate_channel_socket() -> str:
    if sys.platform == "win32":
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.bind(("127.0.0.1", 0))
            port = int(listener.getsockname()[1])
        finally:
            listener.close()
        return f"http://127.0.0.1:{port}"
    return os.path.join(tempfile.gettempdir(), f"psi-g4-{uuid.uuid4().hex[:16]}.sock")


async def _wait_for_session(channel_socket: str, timeout_seconds: float = 30.0) -> None:
    connector, endpoint = resolve_connector_and_endpoint(channel_socket)
    base = endpoint.rsplit("/chat/completions", 1)[0] or "http://localhost"
    deadline = anyio.current_time() + timeout_seconds
    async with aiohttp.ClientSession(connector=connector) as client:
        while anyio.current_time() < deadline:
            try:
                async with client.get(base):
                    return
            except aiohttp.ClientError, OSError:
                await anyio.sleep(0.1)
    raise TimeoutError(f"Agent Session did not become ready within {timeout_seconds}s")


async def _chat_session(
    channel_socket: str,
    message: str,
) -> None:
    async with (
        ChannelCore(session_socket=channel_socket, interval=0.0) as channel,
        aclosing(channel.post([TextChunk(message)])) as stream,
    ):
        async for _chunk in stream:
            pass


async def _final_assistant_reply(
    *,
    workspace: str,
    session_id: str,
) -> str:
    history_path = anyio.Path(workspace) / "histories" / f"{session_id}.jsonl"
    try:
        raw = await history_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError, UnicodeDecodeError) as error:
        raise RuntimeError("Agent Session did not persist a final assistant reply") from error
    lines = [line for line in raw.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("Agent Session did not persist a final assistant reply")
    try:
        final = json.loads(lines[-1])
    except json.JSONDecodeError as error:
        raise RuntimeError("Agent Session history is not valid JSONL") from error
    if not isinstance(final, dict):
        raise RuntimeError("Agent Session history contains an invalid message")
    content = final.get("content")
    if (
        final.get("role") != "assistant"
        or final.get("tool_calls")
        or not isinstance(content, str)
        or not content.strip()
    ):
        raise RuntimeError("Agent Session did not commit a final assistant text reply")
    return content


async def _invoke_agent_session(
    *,
    ai_socket: str,
    workspace: str,
    session_id: str,
    message: str,
) -> str:
    channel_socket = _allocate_channel_socket()
    session = Session(
        ai_socket=ai_socket,
        channel_socket=channel_socket,
        workspace=workspace,
        session_id=session_id,
    )
    try:
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(session.run)
            await _wait_for_session(channel_socket)
            await _chat_session(channel_socket, message)
            text = await _final_assistant_reply(
                workspace=workspace,
                session_id=session_id,
            )
            task_group.cancel_scope.cancel()
        return text
    finally:
        if not channel_socket.startswith(("http://", "https://", "\\\\.\\pipe\\")):
            with anyio.CancelScope(shield=True):
                socket_path = anyio.Path(channel_socket)
                try:
                    if await socket_path.exists():
                        await socket_path.unlink()
                except OSError:
                    pass


def _build_step_completion(
    *,
    ai_socket: str,
    workspace: str,
    work_dir: str,
    run_id: str,
) -> StepCompletion:
    async def complete(
        step: StepNode,
        output_ids: tuple[str, ...],
        inputs: Mapping[str, object],
    ) -> str:
        if not output_ids:
            output_contract = "Return an empty JSON object: {}."
        elif len(output_ids) == 1:
            output_contract = (
                f"Return only the value for output artifact {output_ids[0]!r}. "
                f"A JSON object with the single key {output_ids[0]!r} is also accepted."
            )
        else:
            output_contract = (
                "Return only a JSON object keyed exactly by these output artifact IDs: "
                f"{json.dumps(output_ids, ensure_ascii=False)}."
            )
        message = (
            "Execute exactly one assigned step. Do not plan, author, or start another orchestration.\n"
            f"Step: {step.step_id}\n"
            f"Step name: {step.name_id}\n"
            f"Executor identity: {step.executor_id}\n"
            f"Working directory: {work_dir}\n"
            f"Instruction or reference: {step.instruction_id}\n"
            f"Inputs: {json.dumps(dict(inputs), ensure_ascii=False, sort_keys=True, default=str)}\n"
            f"{output_contract}"
        )
        session_suffix = uuid.uuid4().hex[:8]
        step_digest = sha256(step.step_id.encode()).hexdigest()[:12]
        session_id = f"flow-{run_id}-{step_digest}-{session_suffix}"
        return await _invoke_agent_session(
            ai_socket=ai_socket,
            workspace=workspace,
            session_id=session_id,
            message=message,
        )

    return complete


async def _execute_graph(
    *,
    source: str,
    compiled: CompiledWorkflow,
    plan: ExecutionPlan,
    inputs: Mapping[str, object],
    runs_dir: str,
    run_id: str,
    resume_run_id: str,
    ai_socket: str,
    workspace: str,
    work_dir: str,
    complete_step: StepCompletion | None = None,
) -> dict[str, object]:
    output_ids_by_step = _outputs_by_step(compiled)
    resolved_workspace = str(await anyio.Path(workspace).resolve())
    complete = complete_step or _build_step_completion(
        ai_socket=ai_socket,
        workspace=workspace,
        work_dir=work_dir,
        run_id=run_id,
    )
    handles = {
        step.step_id: _flow.agent(
            _AgentConfig(
                name=step.step_id,
                system=(
                    "Execute one graph step using the supplied instruction and artifact context. "
                    f"The declared executor identity is {step.executor_id!r}."
                ),
                engine=(f"{_RUN_MARKER_KIND}:runner-v{_RUN_MARKER_VERSION}:step-cache-v{_STEP_CACHE_VERSION}"),
            )
        )
        for step in compiled.graph.steps
    }

    async def runner(config: Any, invocation: Any) -> Any:
        step = next(item for item in compiled.graph.steps if item.step_id == config.name)
        context = {key: _context_value(value) for key, value in (invocation.context or {}).items()}
        raw = await complete(step, output_ids_by_step[step.step_id], context)
        normalized = _normalize_step_output(step.step_id, output_ids_by_step[step.step_id], raw)
        return _SessionResult(text=json.dumps(normalized, ensure_ascii=False, sort_keys=True, default=str))

    outputs: dict[str, object] | None = None

    async def program(context: Any) -> None:
        nonlocal outputs
        run_path = anyio.Path(context.run_dir)
        await _atomic_write_json(
            run_path / _RUN_MARKER_NAME,
            {
                "runner": _RUN_MARKER_KIND,
                "version": _RUN_MARKER_VERSION,
                "run_id": run_id,
                "workflow_id": compiled.graph.workflow_id,
            },
        )
        await _atomic_write_text(run_path / "workflow.g4", source)
        await _atomic_write_json(run_path / "workflow-graph.json", compiled.graph.to_dict())
        await _atomic_write_json(run_path / "execution-plan.json", _plan_payload(plan))
        execution_inputs = {
            name: _context_value(await context.input(name, encoded)) for name, encoded in sorted(runtime_inputs.items())
        }

        async def dispatch(step: StepNode, step_inputs: Mapping[str, object]) -> Mapping[str, object]:
            instruction_identity = await _prepare_instruction(
                str(step.instruction_id),
                work_dir=work_dir,
            )
            workspace_identity = await _workspace_cache_identity(
                resolved_workspace,
                ai_socket,
            )
            prompt = (
                f"Step name: {step.name_id}\n"
                f"Executor identity: {step.executor_id}\n"
                f"Instruction cache identity: {instruction_identity}\n"
                f"Workspace execution identity: {workspace_identity}\n"
                f"Input artifact IDs: {json.dumps(sorted(step_inputs), ensure_ascii=False)}\n"
                f"Output artifact IDs: {json.dumps(output_ids_by_step[step.step_id], ensure_ascii=False)}"
            )
            raw = await _flow.session(
                handles[step.step_id],
                prompt,
                {key: _context_text(value) for key, value in step_inputs.items()},
                binding_name=step.step_id,
            )
            parsed = json.loads(raw)
            if not isinstance(parsed, dict) or set(parsed) != set(output_ids_by_step[step.step_id]):
                raise ValueError(f"cached outputs for {step.step_id!r} do not match the graph")
            step_outputs = cast(dict[str, object], parsed)
            for artifact_id, value in step_outputs.items():
                await context.save(artifact_id, _binding_text(value))
            return step_outputs

        try:
            outputs = await _execute_plan(
                plan,
                compiled.graph,
                inputs=execution_inputs,
                dispatch=cast(StepDispatcher, dispatch),
            )
        except ExceptionGroup as error:
            raise _flatten_execution_error(error) from error
        await _atomic_write_json(run_path / "outputs.json", outputs)

    runtime_inputs = {key: _context_text(value) for key, value in inputs.items()}
    await _run_execution(
        program,
        runs_dir=runs_dir,
        inputs=runtime_inputs,
        runner=runner,
        run_id=None if resume_run_id else run_id,
        resume_from_run_id=resume_run_id or None,
        throw_on_error=True,
        program_path=_THIS_FILE,
        keep_count=0,
        keep_days=0,
    )
    if outputs is None:
        raise RuntimeError("workflow execution completed without outputs")
    return outputs


def _argv_flag(flag: str) -> str:
    try:
        index = sys.argv.index(flag)
    except ValueError:
        return ""
    if index + 1 >= len(sys.argv):
        return ""
    return sys.argv[index + 1].strip()


def _resolve_ai_socket() -> str:
    for value in (
        os.environ.get("FLOW_NEXT_AI_SOCKET", ""),
        os.environ.get("FLOW_PSI_AI_SOCKET", ""),
        _argv_flag("--ai-socket"),
    ):
        if value.strip():
            selected = value.strip()
            if selected.startswith(("http://", "https://", "\\\\.\\pipe\\")):
                return selected
            return _absolute_path(os.path.expandvars(os.path.expanduser(selected)))
    return ""


def _resolve_worker_python(raw: str) -> str:
    selected = os.path.expandvars(os.path.expanduser(raw))
    if os.path.dirname(selected):
        return os.path.abspath(selected)
    return selected


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        kernel32 = _KERNEL32
        if kernel32 is None:
            return False
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        exit_code = ctypes.c_ulong()
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        kernel32.CloseHandle(handle)
        return bool(ok) and exit_code.value == _STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


async def _spawn_worker(state_path: anyio.Path, *, cwd: str) -> int:
    configured_python = os.environ.get("FLOW_NEXT_PYTHON", "").strip()
    if configured_python:
        configured_python = _resolve_worker_python(configured_python)
        argv = [configured_python, _THIS_FILE, "--worker", str(state_path)]
    else:
        argv = [sys.executable, _THIS_FILE, "--worker", str(state_path)]
    kwargs: dict[str, Any] = {
        "cwd": cwd,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "start_new_session": True,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_BREAKAWAY_FROM_JOB
    process = await anyio.open_process(argv, **kwargs)
    return int(process.pid or 0)


async def _start(
    *,
    flow_path: str,
    inputs_json: str,
    inputs_path: str,
    cwd: str,
    resume_run_id: str,
) -> dict[str, object]:
    if not flow_path.strip():
        raise ValueError("start requires flow_path")
    base = _absolute_path(cwd.strip() or os.getcwd())
    source_path = _resolve_path(flow_path, base=base)
    if source_path.name.lower().endswith((".ts", ".flow.ts")):
        raise ValueError("run_flow accepts FusionFlow G4 source only, not TypeScript")
    if not await source_path.is_file():
        raise FileNotFoundError(f"workflow file not found: {source_path}")

    requested_work_dir = _absolute_path(cwd.strip()) if cwd.strip() else str(source_path.parent)
    runs_dir = await _prepare_runs_dir(requested_work_dir)
    work_dir = str(anyio.Path(runs_dir).parent)
    inputs = await _load_inputs(inputs_json=inputs_json, inputs_path=inputs_path, base=work_dir)
    source = await source_path.read_text(encoding="utf-8")
    compiled, _plan = _preflight(source, inputs)

    selected_resume = resume_run_id.strip()
    if selected_resume:
        selected_resume = _assert_safe_name(selected_resume)
        if selected_resume == "last":
            raise ValueError("resume_run_id='last' is not supported by run_flow; provide the exact run ID")
        run_id = selected_resume
    else:
        run_id = _make_run_id()

    run_dir = await _resolve_run_dir(runs_dir, run_id, resume=bool(selected_resume))
    if selected_resume:
        await _validate_resume_provenance(
            run_dir,
            run_id,
            compiled.graph.workflow_id,
        )

    ai_socket = _resolve_ai_socket()
    if not ai_socket:
        raise RuntimeError("run_flow requires the current Session AI socket")
    workspace = _absolute_path(os.environ.get("WORKSPACE_DIR", "").strip() or _WORKSPACE_DIR)

    token = _make_run_token()
    attempt_id = _make_attempt_id()
    lock_dir = await _acquire_run_lock(runs_dir, run_id, token)
    worker_started = False
    state_path: anyio.Path | None = None
    try:
        progress_offset = 0
        if selected_resume:
            existing_events = await _read_progress(run_dir)
            progress_offset = len(existing_events)

        state_path = _state_path(token)
        state: dict[str, object] = {
            "run_token": token,
            "attempt_id": attempt_id,
            "run_id": run_id,
            "resume_run_id": selected_resume,
            "run_dir": run_dir,
            "runs_dir": runs_dir,
            "flow_path": str(source_path),
            "source": source,
            "inputs": dict(inputs),
            "work_dir": work_dir,
            "workspace": workspace,
            "ai_socket": ai_socket,
            "started_at": _now_iso(),
            "started_ts": time.time(),
            "cursor": 0,
            "progress_offset": progress_offset,
            "lock_dir": str(lock_dir),
            "pid": 0,
            "log_path": str(state_path.with_suffix(".log")),
        }
        await _atomic_write_json(state_path, state)
        pid = await _spawn_worker(state_path, cwd=work_dir)
        if pid <= 0:
            raise RuntimeError("workspace worker did not return a valid process ID")
        worker_started = True
        state["pid"] = pid
        await _atomic_write_json(state_path, state)
    except BaseException:
        if not worker_started:
            with anyio.CancelScope(shield=True):
                if state_path is not None:
                    with suppress(OSError):
                        if await state_path.exists():
                            await state_path.unlink()
                await _release_run_lock(lock_dir, expected_token=token)
        raise
    return {
        "ok": True,
        "run_token": token,
        "attempt_id": attempt_id,
        "run_id": run_id,
        "run_dir": run_dir,
        "pid": pid,
        "resumed": bool(selected_resume),
        "message": "FusionFlow G4 workflow started in background",
    }


async def _read_progress(run_dir: str) -> list[dict[str, object]]:
    path = anyio.Path(run_dir) / "progress.jsonl"
    try:
        raw = await path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return []
    events: list[dict[str, object]] = []
    for line in raw.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and all(isinstance(key, str) for key in value):
            events.append(cast(dict[str, object], value))
    return events


def _nodes_summary(events: list[dict[str, object]]) -> list[dict[str, object]]:
    nodes: dict[str, dict[str, object]] = {}
    for event in events:
        node_id = event.get("id")
        if not isinstance(node_id, str) or not node_id:
            continue
        row = nodes.setdefault(
            node_id,
            {
                "id": node_id,
                "type": event.get("type", ""),
                "label": event.get("label", ""),
                "status": "running",
            },
        )
        if event.get("event") == "node_end":
            row["status"] = event.get("status", "ok")
            if "durationMs" in event:
                row["durationMs"] = event["durationMs"]
    return list(nodes.values())


async def _tail(path: str, limit: int = 1200) -> str:
    try:
        text = await anyio.Path(path).read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError, OSError:
        return ""
    return text[-limit:]


def _state_attempt_identity(
    token: str,
    state: Mapping[str, object],
) -> tuple[str, str, str]:
    if state.get("run_token") != token:
        raise RuntimeError("run token does not match its persisted state")
    attempt_value = state.get("attempt_id")
    run_id_value = state.get("run_id")
    digest = _run_token_digest(token)
    if not isinstance(attempt_value, str):
        raise RuntimeError("run state is missing attempt_id")
    attempt_id = _validate_attempt_id(attempt_value)
    if not isinstance(run_id_value, str) or not run_id_value:
        raise RuntimeError("run state is missing run_id")
    return run_id_value, attempt_id, digest


async def _read_attempt_terminal(
    token: str,
    state: Mapping[str, object],
) -> dict[str, object] | None:
    run_id, attempt_id, token_digest = _state_attempt_identity(token, state)
    terminal = await _read_json_object(_terminal_path(token))
    if terminal is None:
        return None
    meta = terminal.get("meta")
    if (
        terminal.get("run_token") != token
        or terminal.get("run_id") != run_id
        or terminal.get("attempt_id") != attempt_id
        or not isinstance(meta, dict)
        or meta.get("run_id") != run_id
        or meta.get(_META_ATTEMPT_ID) != attempt_id
        or meta.get(_META_TOKEN_DIGEST) != token_digest
    ):
        raise RuntimeError("run terminal identity does not match its token and attempt")
    return terminal


def _terminal_progress(terminal: Mapping[str, object]) -> list[dict[str, object]]:
    raw = terminal.get("progress", [])
    if not isinstance(raw, list):
        return []
    return [
        cast(dict[str, object], event)
        for event in raw
        if isinstance(event, dict) and all(isinstance(key, str) for key in event)
    ]


async def _status(token: str, window_seconds: float) -> dict[str, object]:
    state_path = _state_path(token)
    state = await _read_json_object(state_path)
    if state is None:
        return {"ok": False, "message": f"unknown run_token: {token}"}

    run_id, attempt_id, _token_digest = _state_attempt_identity(token, state)
    run_dir = str(state.get("run_dir", ""))
    pid_value = state.get("pid", 0)
    pid = pid_value if isinstance(pid_value, int) else 0
    cursor_value = state.get("cursor", 0)
    cursor = cursor_value if isinstance(cursor_value, int) else 0
    started_ts_value = state.get("started_ts", time.time())
    started_ts = float(started_ts_value) if isinstance(started_ts_value, int | float) else time.time()
    deadline = anyio.current_time() + max(1.0, window_seconds)

    while True:
        terminal = await _read_attempt_terminal(token, state)
        if terminal is not None:
            events = _terminal_progress(terminal)
            completed = sum(1 for event in events if event.get("event") == "node_end")
            state["cursor"] = completed
            await _atomic_write_json(state_path, state)
            meta = cast(dict[str, object], terminal["meta"])
            response: dict[str, object] = {
                "ok": True,
                "run_token": token,
                "run_id": run_id,
                "attempt_id": attempt_id,
                "alive": False,
                "done": True,
                "nodes": _nodes_summary(events),
                "completed": completed,
                "elapsed_s": round(time.time() - started_ts, 1),
                "status": meta.get("status", "unknown"),
            }
            if meta.get("error"):
                response["error"] = meta["error"]
            return response

        owner = await _read_json_object(anyio.Path(str(state.get("lock_dir", ""))) / "owner.json")
        alive = _pid_alive(pid) and owner is not None and owner.get("run_token") == token
        if not alive:
            if await _read_attempt_terminal(token, state) is not None:
                continue
            return {
                "ok": True,
                "run_token": token,
                "run_id": run_id,
                "attempt_id": attempt_id,
                "alive": False,
                "done": False,
                "nodes": [],
                "completed": cursor,
                "elapsed_s": round(time.time() - started_ts, 1),
                "crashed": True,
                "log_tail": await _tail(str(state.get("log_path", ""))),
            }

        all_events = await _read_progress(run_dir)
        offset_value = state.get("progress_offset", 0)
        offset = offset_value if isinstance(offset_value, int) and offset_value >= 0 else 0
        events = all_events[offset:]
        completed = sum(1 for event in events if event.get("event") == "node_end")
        if completed > cursor or anyio.current_time() >= deadline:
            state["cursor"] = completed
            await _atomic_write_json(state_path, state)
            response: dict[str, object] = {
                "ok": True,
                "run_token": token,
                "run_id": run_id,
                "attempt_id": attempt_id,
                "alive": alive,
                "done": False,
                "nodes": _nodes_summary(events),
                "completed": completed,
                "elapsed_s": round(time.time() - started_ts, 1),
            }
            return response
        await anyio.sleep(0.5)


async def _read_optional_json(path: anyio.Path) -> object | None:
    try:
        raw = await path.read_text(encoding="utf-8")
        return json.loads(raw)
    except FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError:
        return None


async def _read_bindings(run_dir: anyio.Path) -> dict[str, str]:
    bindings: dict[str, str] = {}
    binding_dir = run_dir / "bindings"
    if not await binding_dir.is_dir():
        return bindings
    paths = [path async for path in binding_dir.glob("*.md")]
    for path in sorted(paths, key=lambda item: item.name):
        try:
            bindings[path.stem] = await path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return bindings


async def _seal_attempt_terminal(
    token: str,
    state: Mapping[str, object],
) -> None:
    run_id, attempt_id, token_digest = _state_attempt_identity(token, state)
    run_dir = anyio.Path(str(state.get("run_dir", "")))
    meta_path = run_dir / "meta.json"
    meta = await _read_json_object(meta_path)
    if meta is None or meta.get("run_id") != run_id:
        raise RuntimeError("workflow runtime did not persist meta for this attempt")
    meta[_META_ATTEMPT_ID] = attempt_id
    meta[_META_TOKEN_DIGEST] = token_digest
    await _atomic_write_json(meta_path, meta)

    status = meta.get("status", "unknown")
    all_events = await _read_progress(str(run_dir))
    offset_value = state.get("progress_offset", 0)
    offset = offset_value if isinstance(offset_value, int) and offset_value >= 0 else 0
    terminal: dict[str, object] = {
        "run_token": token,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "run_dir": str(run_dir),
        "meta": meta,
        "outputs": await _read_optional_json(run_dir / "outputs.json") if status == "ok" else None,
        "bindings": await _read_bindings(run_dir) if status == "ok" else {},
        "workflow_graph": await _read_optional_json(run_dir / "workflow-graph.json") if status == "ok" else None,
        "execution_graph": await _read_optional_json(run_dir / "execution-graph.json"),
        "progress": all_events[offset:],
    }
    terminal_path = _terminal_path(token)
    if await terminal_path.exists():
        raise RuntimeError("run attempt terminal already exists")
    await _atomic_write_json(terminal_path, terminal)


async def _result(token: str) -> dict[str, object]:
    state = await _read_json_object(_state_path(token))
    if state is None:
        return {"ok": False, "message": f"unknown run_token: {token}"}
    run_id, attempt_id, _token_digest = _state_attempt_identity(token, state)
    terminal = await _read_attempt_terminal(token, state)
    if terminal is None:
        return {"ok": False, "message": "current run has not finished yet", "done": False}
    meta = cast(dict[str, object], terminal["meta"])
    status = meta.get("status", "unknown")
    return {
        "ok": True,
        "run_token": token,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "run_dir": terminal.get("run_dir", state.get("run_dir", "")),
        "status": status,
        "meta": meta,
        "outputs": terminal.get("outputs") if status == "ok" else None,
        "bindings": terminal.get("bindings", {}),
        "workflow_graph": terminal.get("workflow_graph"),
        "execution_graph": terminal.get("execution_graph"),
    }


async def _worker(state_path: anyio.Path) -> None:
    state = await _read_json_object(state_path)
    if state is None:
        raise ValueError(f"invalid worker state: {state_path}")
    log_path = anyio.Path(str(state.get("log_path", "")))
    lock_value = str(state.get("lock_dir", ""))
    lock_dir = anyio.Path(lock_value) if lock_value else None
    run_token = str(state.get("run_token", ""))
    caught: BaseException | None = None
    seal_error: BaseException | None = None
    meta_cleared = False
    try:
        try:
            if lock_dir is not None:
                await _set_run_lock_pid(lock_dir, run_token, os.getpid())
            source = state.get("source")
            inputs = state.get("inputs")
            if not isinstance(source, str) or not isinstance(inputs, dict):
                raise ValueError("worker state is missing source or inputs")
            if not all(isinstance(key, str) for key in inputs):
                raise ValueError("worker inputs must have string keys")
            typed_inputs = cast(dict[str, object], inputs)
            compiled, plan = _preflight(source, typed_inputs)
            if state.get("resume_run_id"):
                meta_path = anyio.Path(str(state.get("run_dir", ""))) / "meta.json"
                with suppress(FileNotFoundError):
                    await meta_path.unlink()
            meta_cleared = True
            await _execute_graph(
                source=source,
                compiled=compiled,
                plan=plan,
                inputs=typed_inputs,
                runs_dir=str(state.get("runs_dir", "")),
                run_id=str(state.get("run_id", "")),
                resume_run_id=str(state.get("resume_run_id", "")),
                ai_socket=str(state.get("ai_socket", "")),
                workspace=str(state.get("workspace", "")),
                work_dir=str(state.get("work_dir", "")),
            )
        except BaseException as error:
            caught = error

        if meta_cleared:
            with anyio.CancelScope(shield=True):
                try:
                    await _seal_attempt_terminal(run_token, state)
                except BaseException as error:
                    seal_error = error
                    if caught is None:
                        caught = error

        if caught is not None:
            details = f"{caught.__class__.__name__}: {caught}\n"
            if seal_error is not None and seal_error is not caught:
                details += f"TerminalSealError: {seal_error}\n"
            with anyio.CancelScope(shield=True):
                with suppress(OSError):
                    await _atomic_write_text(log_path, details)
    finally:
        if lock_dir is not None:
            with anyio.CancelScope(shield=True):
                with suppress(OSError):
                    await _release_run_lock(lock_dir, expected_token=run_token)
    if caught is not None:
        raise caught


async def _worker_cli() -> None:
    if len(sys.argv) != 3 or sys.argv[1] != "--worker":
        raise ValueError("run_flow.py is an internal worker; invoke the run_flow tool")
    await _worker(anyio.Path(sys.argv[2]))


async def run_flow(
    action: str,
    flow_path: str = "",
    inputs_json: str = "",
    inputs_path: str = "",
    run_token: str = "",
    cwd: str = "",
    window_seconds: float = 60.0,
    resume_run_id: str = "",
) -> str:
    """Run a FusionFlow Next G4 workflow with start/status/result polling.

    Args:
        action: ``start`` | ``status`` | ``result``.
        flow_path: (start) G4 workflow source path. TypeScript is rejected.
        inputs_json: (start) JSON object keyed by every input Artifact ID.
        inputs_path: (start) JSON input file; mutually exclusive with inputs_json.
        run_token: (status/result) opaque token returned by start.
        cwd: (start) source/run working directory; defaults to the source directory.
        window_seconds: (status) keepalive window while waiting for progress.
        resume_run_id: (start) exact prior run ID to resume in place.

    Returns:
        JSON. ``start`` returns the run token, ID, directory, and worker PID;
        ``status`` returns node progress and terminal state; ``result`` returns
        output Artifacts, bindings, and static/dynamic execution graphs.
    """

    try:
        selected = action.strip().lower()
        if selected == "start":
            result = await _start(
                flow_path=flow_path,
                inputs_json=inputs_json,
                inputs_path=inputs_path,
                cwd=cwd,
                resume_run_id=resume_run_id,
            )
        elif selected == "status":
            if not run_token:
                result = {"ok": False, "message": "status requires run_token"}
            else:
                result = await _status(run_token, window_seconds)
        elif selected == "result":
            if not run_token:
                result = {"ok": False, "message": "result requires run_token"}
            else:
                result = await _result(run_token)
        else:
            result = {
                "ok": False,
                "message": f"unknown action {action!r}; use start|status|result",
            }
    except Exception as error:
        result = {
            "ok": False,
            "message": str(error) or error.__class__.__name__,
            "error_type": error.__class__.__name__,
        }
    return json.dumps(result, ensure_ascii=False)


if __name__ == "__main__":
    anyio.run(_worker_cli)
