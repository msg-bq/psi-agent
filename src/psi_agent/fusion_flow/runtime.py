from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from hashlib import sha256
from os import PathLike
from uuid import uuid4

import anyio
from loguru import logger

from .model import (
    ExecutionTrace,
    RunResult,
    SessionRunner,
    TraceKind,
    TraceStatus,
    aggregate_tokens,
    assert_safe_name,
)

type Program = Callable[[RunContext], Awaitable[object]]
type PathValue = str | PathLike[str] | anyio.Path

_CURRENT_RUN: ContextVar[RunContext | None] = ContextVar(
    "fusion_flow_current_run",
    default=None,
)
_CURRENT_TRACE: ContextVar[ExecutionTrace | None] = ContextVar(
    "fusion_flow_current_trace",
    default=None,
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _make_run_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{uuid4().hex[:6]}"


def _error_text(error: BaseException) -> str:
    text = str(error)
    return text or error.__class__.__name__


def stable_payload_hash(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(payload.encode("utf-8")).hexdigest()


async def _atomic_write_text(path: anyio.Path, value: str) -> None:
    temporary = anyio.Path(path.parent, f".{path.name}.tmp-{uuid4().hex}")
    try:
        await temporary.write_text(value, encoding="utf-8")
        await temporary.replace(path)
    finally:
        with anyio.CancelScope(shield=True):
            if await temporary.exists():
                await temporary.unlink()


async def _atomic_write_json(
    path: anyio.Path,
    value: Mapping[str, object],
) -> None:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    await _atomic_write_text(path, f"{payload}\n")


async def _remove_tree(path: anyio.Path) -> None:
    if await path.is_symlink():
        await path.unlink()
        return
    async for child in path.iterdir():
        if await child.is_symlink() or not await child.is_dir():
            await child.unlink()
        else:
            await _remove_tree(child)
    await path.rmdir()


async def _resolve_direct_child(
    path: anyio.Path,
    parent: anyio.Path,
    *,
    label: str,
) -> anyio.Path:
    if await path.is_symlink():
        raise ValueError(f"{label} must not be a symbolic link")
    resolved = await path.resolve()
    if resolved != anyio.Path(parent, path.name):
        raise ValueError(f"{label} escapes its parent directory")
    return resolved


async def _ensure_run_subdirectory(
    run_dir: anyio.Path,
    name: str,
) -> anyio.Path:
    path = anyio.Path(run_dir, name)
    if await path.exists():
        if not await path.is_dir():
            raise ValueError(f'run path "{name}" must be a directory')
    else:
        await path.mkdir()
    return await _resolve_direct_child(
        path,
        run_dir,
        label=f'run path "{name}"',
    )


class RunContext:
    """Mutable state owned by exactly one ``run()`` invocation."""

    def __init__(
        self,
        *,
        run_id: str,
        run_dir: anyio.Path,
        inputs: Mapping[str, str],
        runner: SessionRunner | None,
        root_trace: ExecutionTrace,
        resumed: bool,
        resume_bindings: Mapping[str, str],
    ) -> None:
        self.run_id = run_id
        self.run_dir = str(run_dir)
        self.runner = runner
        self.root_trace = root_trace
        self.resumed = resumed
        self._path = run_dir
        self._inputs = dict(inputs)
        self._resume_bindings = dict(resume_bindings)
        self._resume_metadata: dict[str, dict[str, object]] = {}
        self._services: dict[str, object] = {}
        self._blocks: dict[str, object] = {}
        self._input_names: set[str] = set()
        self._binding_names: set[str] = set(resume_bindings)
        self._binding_reservations: set[str] = set()
        self._call_counts: dict[str, int] = {}
        self._lock = anyio.Lock()
        self._sealed = False

    async def input(self, name: str, default_value: str) -> str:
        """Read and persist one named input using the run's injected overrides."""
        self._ensure_open()
        async with self._trace("input", name) as trace:
            value = await self._read_input(name, default_value)
            trace.output_summary = value
            return value

    async def save(self, name: str, value: str) -> None:
        """Persist one named binding through the same single-assignment path."""
        self._ensure_open()
        preview = repr(value)
        async with self._trace(
            "output",
            name,
            input_summary=preview if len(preview) <= 60 else f"{preview[:57]}...",
        ) as trace:
            await self._commit_binding(
                name,
                value,
                metadata=self._binding_metadata(
                    name,
                    produced_by="flow.output",
                    operation="output",
                    source_node=trace.trace_id,
                ),
            )
            trace.output_summary = value

    @property
    def services(self) -> dict[str, object]:
        return self._services

    @property
    def blocks(self) -> dict[str, object]:
        return self._blocks

    def _ensure_open(self) -> None:
        if self._sealed:
            raise RuntimeError("run context is sealed")

    def _binding_metadata(
        self,
        name: str,
        *,
        produced_by: str,
        tokens: Mapping[str, int | None] | None = None,
        **details: object,
    ) -> dict[str, object]:
        trace = _CURRENT_TRACE.get() or self.root_trace
        metadata: dict[str, object] = {
            "name": name,
            "produced_by": produced_by,
            "produced_at": _now_iso(),
            "source_node": trace.trace_id,
        }
        if tokens is not None:
            metadata["tokens"] = dict(tokens)
        metadata.update(details)
        return metadata

    async def _read_input(self, name: str, default_value: str) -> str:
        normalized = assert_safe_name(name)
        if not isinstance(default_value, str):
            raise TypeError("input default_value must be a string")
        async with self._lock:
            self._ensure_open()
            if normalized in self._input_names:
                raise ValueError(f'input "{normalized}" was already read')
            self._input_names.add(normalized)

        value = self._inputs.get(normalized, default_value)
        if not isinstance(value, str):
            with anyio.CancelScope(shield=True):
                async with self._lock:
                    self._input_names.discard(normalized)
            raise TypeError(f'input "{normalized}" must be a string')
        try:
            await _atomic_write_text(
                anyio.Path(self._path, "input", f"{normalized}.md"),
                value,
            )
        except BaseException:
            with anyio.CancelScope(shield=True):
                async with self._lock:
                    self._input_names.discard(normalized)
            raise
        return value

    async def _reserve_binding(self, name: str) -> str:
        normalized = assert_safe_name(name)
        async with self._lock:
            self._ensure_open()
            if normalized in self._binding_names or normalized in self._binding_reservations:
                raise ValueError(f'binding "{normalized}" already exists')
            self._binding_reservations.add(normalized)
        return normalized

    async def _release_binding(self, name: str) -> None:
        with anyio.CancelScope(shield=True):
            async with self._lock:
                self._binding_reservations.discard(name)

    async def _reserve_auto_binding(self, base: str) -> str:
        normalized = assert_safe_name(base)
        suffix = 1
        while True:
            candidate = normalized if suffix == 1 else f"{normalized}.{suffix}"
            try:
                return await self._reserve_binding(candidate)
            except ValueError:
                suffix += 1

    async def _next_call_name(self, base: str) -> str:
        normalized = assert_safe_name(base)
        async with self._lock:
            self._ensure_open()
            count = self._call_counts.get(normalized, 0) + 1
            self._call_counts[normalized] = count
        return normalized if count == 1 else f"{normalized}.{count}"

    async def _commit_reserved_binding(
        self,
        name: str,
        value: str,
        *,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        if not isinstance(value, str):
            await self._release_binding(name)
            raise TypeError("binding value must be a string")

        metadata_payload = dict(metadata or {})
        trace = _CURRENT_TRACE.get() or self.root_trace
        metadata_payload.setdefault("name", name)
        metadata_payload.setdefault(
            "produced_by",
            str(metadata_payload.get("operation", "run")),
        )
        metadata_payload.setdefault("produced_at", _now_iso())
        metadata_payload.setdefault("source_node", trace.trace_id)
        try:
            json.dumps(metadata_payload)
        except (TypeError, ValueError) as error:
            await self._release_binding(name)
            raise TypeError("binding metadata must be JSON serializable") from error

        binding_path = anyio.Path(self._path, "bindings", f"{name}.md")
        metadata_path = anyio.Path(self._path, "bindings", f"{name}.meta.json")
        try:
            self._ensure_open()
            await _atomic_write_json(
                metadata_path,
                metadata_payload,
            )
            await _atomic_write_text(binding_path, value)

            async with self._lock:
                self._ensure_open()
                self._binding_reservations.remove(name)
                self._binding_names.add(name)
        except BaseException:
            with anyio.CancelScope(shield=True):
                if await binding_path.exists():
                    await binding_path.unlink()
                if await metadata_path.exists():
                    await metadata_path.unlink()
                await self._release_binding(name)
            raise

    async def _commit_binding(
        self,
        name: str,
        value: str,
        *,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        normalized = await self._reserve_binding(name)
        await self._commit_reserved_binding(
            normalized,
            value,
            metadata=metadata,
        )

    def _resume_binding(self, name: str) -> str | None:
        return self._resume_bindings.get(name)

    def _resume_binding_metadata(self, name: str) -> dict[str, object] | None:
        payload = self._resume_metadata.get(name)
        if payload is None:
            return None
        return dict(payload)

    def _resume_lookup(
        self,
        binding_name: str,
        *,
        cache_key: str | None,
        operation: str,
    ) -> str | None:
        cached = self._resume_binding(binding_name)
        if cached is None:
            return None
        metadata = self._resume_binding_metadata(binding_name)
        if metadata is None:
            return None
        if metadata.get("operation") != operation:
            return None
        if cache_key is not None and metadata.get("cache_key") != cache_key:
            return None
        return cached

    def _register(
        self,
        registry: dict[str, object],
        name: str,
        value: object,
        *,
        kind: str,
    ) -> str:
        normalized = assert_safe_name(name)
        self._ensure_open()
        if normalized in registry:
            raise ValueError(f'{kind} "{normalized}" is already defined')
        registry[normalized] = value
        return normalized

    async def _append_child(
        self,
        parent: ExecutionTrace,
        child: ExecutionTrace,
    ) -> None:
        async with self._lock:
            self._ensure_open()
            parent.children = (*parent.children, child)

    async def _record_progress(self, trace: ExecutionTrace) -> None:
        line = json.dumps(
            trace.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
        )
        async with self._lock:
            stream = await anyio.Path(
                self._path,
                "progress.jsonl",
            ).open("a", encoding="utf-8")
            async with stream:
                await stream.write(f"{line}\n")

    @asynccontextmanager
    async def _trace(
        self,
        kind: TraceKind,
        label: str,
        *,
        input_summary: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> AsyncIterator[ExecutionTrace]:
        parent = _CURRENT_TRACE.get() or self.root_trace
        trace = ExecutionTrace(
            trace_id=f"{kind}-{uuid4().hex[:12]}",
            kind=kind,
            label=label,
            started_at=_now_iso(),
            input_summary=input_summary,
            metadata=dict(metadata or {}),
        )
        await self._append_child(parent, trace)
        token = _CURRENT_TRACE.set(trace)
        started = time.perf_counter()
        try:
            yield trace
        except BaseException as error:
            cancelled = isinstance(error, anyio.get_cancelled_exc_class())
            with anyio.CancelScope(shield=cancelled):
                trace.status = "cancelled" if cancelled else "error"
                trace.error = _error_text(error)
                trace.finished_at = _now_iso()
                trace.duration_ms = (time.perf_counter() - started) * 1_000
                try:
                    await self._record_progress(trace)
                except Exception as progress_error:
                    logger.error(
                        f"Failed to persist trace {trace.trace_id} while handling "
                        f"{error.__class__.__name__}: {progress_error}",
                    )
            raise
        else:
            trace.status = "ok"
            trace.finished_at = _now_iso()
            trace.duration_ms = (time.perf_counter() - started) * 1_000
            try:
                await self._record_progress(trace)
            except Exception as progress_error:
                logger.error(
                    f"Failed to persist completed trace {trace.trace_id}: {progress_error}",
                )
        finally:
            _CURRENT_TRACE.reset(token)

    async def _seal(self) -> None:
        async with self._lock:
            self._sealed = True

    async def _write_trace_file(
        self,
        name: str,
        trace: ExecutionTrace,
    ) -> None:
        try:
            await _atomic_write_json(
                anyio.Path(self._path, "trace", f"{assert_safe_name(name)}.json"),
                trace.to_dict(),
            )
        except Exception as error:
            logger.error(f'Failed to persist diagnostic trace "{name}": {error}')


def current_run_context() -> RunContext:
    context = _CURRENT_RUN.get()
    if context is None:
        raise RuntimeError("flow operation requires an active run() context")
    return context


async def _load_resume_bindings(run_dir: anyio.Path) -> dict[str, str]:
    bindings: dict[str, str] = {}
    directory = anyio.Path(run_dir, "bindings")
    if not await directory.exists():
        return bindings
    if not await directory.is_dir():
        raise ValueError('resume path "bindings" must be a directory')
    directory = await _resolve_direct_child(
        directory,
        run_dir,
        label='resume path "bindings"',
    )
    async for path in directory.iterdir():
        if not path.name.endswith(".md"):
            continue
        if await path.is_symlink():
            raise ValueError(f'resume binding "{path.name}" must not be a symbolic link')
        if not await path.is_file():
            continue
        path = await _resolve_direct_child(
            path,
            directory,
            label=f'resume binding "{path.name}"',
        )
        name = path.name.removesuffix(".md")
        try:
            normalized = assert_safe_name(name)
        except ValueError:
            continue
        if normalized in bindings:
            raise ValueError(
                f'duplicate resume binding after NFC normalization: "{normalized}"',
            )
        bindings[normalized] = await path.read_text(encoding="utf-8")
    return bindings


async def _load_resume_metadata(run_dir: anyio.Path) -> dict[str, dict[str, object]]:
    payloads: dict[str, dict[str, object]] = {}
    directory = anyio.Path(run_dir, "bindings")
    if not await directory.exists():
        return payloads
    if not await directory.is_dir():
        raise ValueError('resume path "bindings" must be a directory')
    directory = await _resolve_direct_child(
        directory,
        run_dir,
        label='resume path "bindings"',
    )
    async for path in directory.iterdir():
        if not path.name.endswith(".meta.json"):
            continue
        if await path.is_symlink():
            raise ValueError(
                f'resume binding metadata "{path.name}" must not be a symbolic link',
            )
        if not await path.is_file():
            continue
        path = await _resolve_direct_child(
            path,
            directory,
            label=f'resume binding metadata "{path.name}"',
        )
        name = path.name.removesuffix(".meta.json")
        try:
            normalized = assert_safe_name(name)
        except ValueError:
            continue
        if normalized in payloads:
            raise ValueError(
                f'duplicate resume metadata after NFC normalization: "{normalized}"',
            )
        raw = json.loads(await path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(
                f'corrupt resume metadata "{path.name}": expected a JSON object',
            )
        payloads[normalized] = dict(raw)
    return payloads


async def _persist_final_state(
    context: RunContext,
    *,
    status: TraceStatus,
    started_at: str,
    started: float,
    error: BaseException | None,
    resume_from_run_id: str | None,
    program_snapshot: str | None,
) -> None:
    finished_at = _now_iso()
    duration_ms = (time.perf_counter() - started) * 1_000
    context.root_trace.status = status
    context.root_trace.finished_at = finished_at
    context.root_trace.duration_ms = duration_ms
    if error is not None:
        context.root_trace.error = _error_text(error)
    tokens = aggregate_tokens(context.root_trace)

    await _atomic_write_json(
        anyio.Path(context._path, "execution-graph.json"),
        {
            "run_id": context.run_id,
            "root": context.root_trace.to_dict(),
        },
    )
    await _atomic_write_json(
        anyio.Path(context._path, "meta.json"),
        {
            "run_id": context.run_id,
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": duration_ms,
            "status": status,
            "error": _error_text(error) if error is not None else None,
            "resumed": resume_from_run_id is not None,
            "resume_from_run_id": resume_from_run_id,
            "program_snapshot": program_snapshot,
            "tokens": {
                "calls": tokens.calls,
                "input": tokens.input,
                "output": tokens.output,
            },
        },
    )


async def run(
    program: Program,
    *,
    runs_dir: PathValue = "runs",
    inputs: Mapping[str, str] | None = None,
    runner: SessionRunner | None = None,
    run_id: str | None = None,
    resume_from_run_id: str | None = None,
    throw_on_error: bool = False,
    program_path: PathValue | None = None,
) -> RunResult:
    """Execute one FusionFlow program and persist its dynamic trace."""

    if run_id is not None and resume_from_run_id is not None:
        raise ValueError("run_id and resume_from_run_id are mutually exclusive")
    selected_id = assert_safe_name(
        resume_from_run_id or run_id or _make_run_id(),
    )
    root = anyio.Path(runs_dir)
    resumed = resume_from_run_id is not None

    normalized_inputs: dict[str, str] = {}
    for name, value in (inputs or {}).items():
        normalized = assert_safe_name(name)
        if not isinstance(value, str):
            raise TypeError(f'input "{normalized}" must be a string')
        if normalized in normalized_inputs:
            raise ValueError(
                f'duplicate input after NFC normalization: "{normalized}"',
            )
        normalized_inputs[normalized] = value

    created_run = False
    try:
        if resumed:
            if not await root.exists():
                raise FileNotFoundError(
                    f'resume run "{selected_id}" does not exist in {root}',
                )
            root_resolved = await root.resolve()
            candidate = anyio.Path(root, selected_id)
            if await candidate.is_symlink():
                raise ValueError(f'resume run "{selected_id}" must not be a symbolic link')
            if not await candidate.is_dir():
                raise FileNotFoundError(
                    f'resume run "{selected_id}" does not exist in {root}',
                )
            run_path = await _resolve_direct_child(
                candidate,
                root_resolved,
                label=f'resume run "{selected_id}"',
            )
        else:
            await root.mkdir(parents=True, exist_ok=True)
            root_resolved = await root.resolve()
            run_path = anyio.Path(root_resolved, selected_id)
            await run_path.mkdir()
            created_run = True
            run_path = await _resolve_direct_child(
                run_path,
                root_resolved,
                label=f'run "{selected_id}"',
            )

        for directory in ("input", "bindings", "trace"):
            await _ensure_run_subdirectory(run_path, directory)

        snapshot_status: str | None = None
        if program_path is not None:
            source = anyio.Path(program_path)
            if await source.is_file():
                await _atomic_write_text(
                    anyio.Path(run_path, "program.py"),
                    await source.read_text(encoding="utf-8"),
                )
                snapshot_status = str(source)
            else:
                snapshot_status = f"unavailable: {source}"

        started_at = _now_iso()
        started = time.perf_counter()
        root_trace = ExecutionTrace(
            trace_id="run-root",
            kind="run",
            label=selected_id,
            started_at=started_at,
        )
        context = RunContext(
            run_id=selected_id,
            run_dir=run_path,
            inputs=normalized_inputs,
            runner=runner,
            root_trace=root_trace,
            resumed=resumed,
            resume_bindings=await _load_resume_bindings(run_path) if resumed else {},
        )
        if resumed:
            context._resume_metadata = await _load_resume_metadata(run_path)
        else:
            try:
                await gc_runs(root_resolved, exclude_run_id=selected_id)
            except Exception as cleanup_error:
                logger.warning(
                    f"Automatic FusionFlow run cleanup failed: {cleanup_error}",
                )
    except BaseException:
        if created_run:
            with anyio.CancelScope(shield=True):
                try:
                    if await run_path.exists():
                        await _remove_tree(run_path)
                except Exception as cleanup_error:
                    logger.error(
                        f'Failed to clean incomplete run "{selected_id}": {cleanup_error}',
                    )
        raise

    run_token = _CURRENT_RUN.set(context)
    trace_token = _CURRENT_TRACE.set(root_trace)
    status: TraceStatus = "ok"
    caught: BaseException | None = None
    persistence_error: BaseException | None = None
    try:
        try:
            await program(context)
        except BaseException as error:
            caught = error
            status = "cancelled" if isinstance(error, anyio.get_cancelled_exc_class()) else "error"
        with anyio.CancelScope(shield=True):
            try:
                await context._seal()
                await _persist_final_state(
                    context,
                    status=status,
                    started_at=started_at,
                    started=started,
                    error=caught,
                    resume_from_run_id=resume_from_run_id,
                    program_snapshot=snapshot_status,
                )
            except BaseException as error:
                persistence_error = error
    finally:
        _CURRENT_TRACE.reset(trace_token)
        _CURRENT_RUN.reset(run_token)

    if persistence_error is not None:
        if caught is not None and isinstance(caught, anyio.get_cancelled_exc_class()):
            logger.error(
                f"Failed to persist cancelled FusionFlow run {selected_id}: {persistence_error}",
            )
        else:
            if caught is not None:
                logger.error(
                    f"FusionFlow run {selected_id} also failed before final-state "
                    f"persistence failed: {_error_text(caught)}",
                )
            raise persistence_error

    logger.info(
        f"FusionFlow run {selected_id} finished with status={status} "
        f"in {(time.perf_counter() - started) * 1_000:.1f}ms",
    )
    if caught is not None and (
        isinstance(caught, anyio.get_cancelled_exc_class()) or not isinstance(caught, Exception) or throw_on_error
    ):
        raise caught
    return RunResult(
        run_id=selected_id,
        run_dir=str(run_path),
        status="error" if status == "error" else "ok",
    )


async def gc_runs(
    runs_dir: PathValue,
    *,
    keep_count: int = 50,
    keep_days: int = 7,
    exclude_run_id: str | None = None,
) -> tuple[str, ...]:
    """Remove direct child run directories outside the retention union."""

    if isinstance(keep_count, bool) or not isinstance(keep_count, int):
        raise TypeError("keep_count must be an integer")
    if isinstance(keep_days, bool) or not isinstance(keep_days, int):
        raise TypeError("keep_days must be an integer")
    if exclude_run_id is not None:
        exclude_run_id = assert_safe_name(exclude_run_id)
    if keep_count < 0 or keep_days < 0:
        raise ValueError("keep_count and keep_days must be non-negative")

    root = anyio.Path(runs_dir)
    if not await root.exists():
        return ()
    root_resolved = await root.resolve()
    candidates: list[tuple[str, float, anyio.Path]] = []
    async for child in root.iterdir():
        if child.name == exclude_run_id:
            continue
        try:
            assert_safe_name(child.name)
        except ValueError:
            continue
        if await child.is_symlink() or not await child.is_dir():
            continue
        resolved = await child.resolve()
        if resolved.parent != root_resolved:
            continue
        stat = await child.stat(follow_symlinks=False)
        candidates.append((child.name, stat.st_mtime, child))

    candidates.sort(key=lambda item: (item[1], item[0]), reverse=True)
    keep: set[str] = set()
    if keep_count > 0:
        keep.update(name for name, _, _ in candidates[:keep_count])
    if keep_days > 0:
        cutoff = time.time() - keep_days * 24 * 60 * 60
        keep.update(name for name, mtime, _ in candidates if mtime >= cutoff)

    deleted: list[str] = []
    for name, _, path in candidates:
        if name in keep:
            continue
        try:
            await _remove_tree(path)
        except Exception as error:
            logger.warning(f'Failed to remove FusionFlow run "{name}": {error}')
        else:
            deleted.append(name)
    return tuple(deleted)
