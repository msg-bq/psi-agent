"""Compile and execute one FusionFlow G4 workflow."""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Mapping
from contextlib import aclosing
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

import anyio

from psi_agent.session.agent import SessionAgent, current_tool_ai_socket
from psi_agent.session.ai_client import AiClient
from psi_agent.session.conversation import Conversation
from psi_agent.session.schedule_registry import ScheduleRegistry
from psi_agent.session.tool_registry import FileEntry, ToolFunction, ToolRegistry
from psi_agent.workflow_execution import ExecutionCheckpoint, ResourceCapacity

_WORKSPACE_DIR = Path(__file__).parent.parent
_SKILL_DIR = _WORKSPACE_DIR / "skills" / "fusion-flow"
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))

from fusion_flow_next.job_store import (  # noqa: E402
    HumanRequestSpec,
    HumanWorkflowRun,
    JobStore,
    RunLease,
)
from fusion_flow_next.workflow_runner import (  # noqa: E402
    CompletionContext,
    ProgramInvocation,
    compile_workflow,
)
from fusion_flow_next.workflow_runner import execute_workflow as _execute_workflow  # noqa: E402

_STEP_SYSTEM_PROMPT = (
    "You execute exactly one assigned FusionFlow Agent step. "
    "Follow the step instruction and inputs in the user message, using workspace tools when needed. "
    "Do not perform workspace onboarding and do not start another workflow. "
    "Your final response must follow the requested JSON output contract exactly."
)
_HUMAN_PREPARER_SYSTEM_PROMPT = (
    "You prepare exactly one assigned FusionFlow Human step for another person. "
    "Use the workspace-confined read tool only when useful to inspect an instruction reference. "
    "Do not change files, perform the task, ask the person directly, or start another workflow. "
    "Your final response must be exactly the requested JSON question contract."
)
_STEP_TOOL_SESSION_ID = f"{__name__}_step"
_STEP_TOOLS_LOAD_LOCK = anyio.Lock()
_STEP_TOOLS_SOURCE: ToolRegistry | None = None
_WORKFLOW_LAUNCHERS = frozenset({"flow_run", "run_flow", "run_flow_resume"})
_NESTED_TURN_TOOLS = frozenset({"clarify"})
_HUMAN_PREPARER_TOOLS = frozenset({"read"})
_HUMAN_CONTROL_KEY = "$fusion_flow/control"
_PROGRAM_TIMEOUT_SECONDS = 300
_JOB_STORE_RELATIVE_PATH = Path(".psi") / "fusion-flow" / "runs"


@dataclass(frozen=True, slots=True)
class _PreparedHumanQuestion:
    question: str
    options: tuple[str, ...] = ()
    recommended: int = 0
    default: str = ""


class _HumanInputRequiredError(Exception):
    """Internal control flow used to end a turn at one Human Step."""

    def __init__(self, request: HumanRequestSpec) -> None:
        super().__init__(f"Human input required for step {request.step_id!r}")
        self.request = request


class _StepToolRegistry(ToolRegistry):
    async def refresh(self) -> dict[str, str]:
        return {}


class _StepScheduleRegistry(ScheduleRegistry):
    async def refresh(self) -> dict[str, str]:
        return {}


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON constant is not supported: {value}")


def _parse_mapping(value: str, *, label: str) -> dict[str, object]:
    try:
        parsed = json.loads(value, parse_constant=_reject_json_constant)
    except (json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} must be a JSON object") from error
    if not isinstance(parsed, dict) or not all(isinstance(key, str) for key in parsed):
        raise ValueError(f"{label} must be a JSON object with string keys")
    return cast(dict[str, object], parsed)


def _parse_resource_capacities(value: str) -> Mapping[str, ResourceCapacity] | None:
    if not value.strip():
        return None

    parsed = _parse_mapping(value, label="resource_capacities_json")
    capacities: dict[str, ResourceCapacity] = {}
    for resource_id, capacity in parsed.items():
        if type(capacity) is int:
            capacities[resource_id] = capacity
        elif isinstance(capacity, list) and all(isinstance(instance_id, str) for instance_id in capacity):
            capacities[resource_id] = tuple(cast(list[str], capacity))
        else:
            raise ValueError(
                f"resource capacity for {resource_id!r} must be an integer or an array of resource instance IDs"
            )
    return capacities


def _parse_human_response(value: str) -> object:
    try:
        return json.loads(value, parse_constant=_reject_json_constant)
    except (json.JSONDecodeError, ValueError) as error:
        raise ValueError("human_response_json must be valid JSON") from error


def _json_values_equal(left: object, right: object) -> bool:
    """Compare JSON values without Python's bool/int equality coercion."""

    return json.dumps(left, ensure_ascii=False, sort_keys=True, separators=(",", ":")) == json.dumps(
        right,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _parse_prepared_human_question(value: str) -> _PreparedHumanQuestion:
    payload = _parse_mapping(value, label="Human instruction preparer response")
    expected_keys = {"question", "options", "recommended", "default"}
    if set(payload) != expected_keys:
        raise ValueError(
            "Human instruction preparer response must contain exactly question, options, recommended, and default"
        )

    question = payload["question"]
    options = payload["options"]
    recommended = payload["recommended"]
    default = payload["default"]
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Human instruction preparer question must be a non-empty string")
    if not isinstance(options, list) or not all(isinstance(option, str) and option.strip() for option in options):
        raise ValueError("Human instruction preparer options must be an array of non-empty strings")
    if len(options) > 4:
        raise ValueError("Human instruction preparer options must contain at most four entries")
    if type(recommended) is not int or not 0 <= recommended <= len(options):
        raise ValueError(f"Human instruction preparer recommended must be between 0 and {len(options)}")
    if not isinstance(default, str):
        raise ValueError("Human instruction preparer default must be a string")
    typed_options = cast(list[str], options)
    return _PreparedHumanQuestion(
        question=question.strip(),
        options=tuple(option.strip() for option in typed_options),
        recommended=recommended,
        default=default.strip(),
    )


def _prepared_question_json(question: _PreparedHumanQuestion) -> str:
    return json.dumps(
        {
            "question": question.question,
            "options": list(question.options),
            "recommended": question.recommended,
            "default": question.default,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _human_response_outputs(
    request: HumanRequestSpec,
    response: object,
) -> dict[str, object]:
    output_ids = request.output_artifact_ids
    if not output_ids:
        return {}
    if len(output_ids) == 1:
        return {output_ids[0]: response}
    if not isinstance(response, Mapping) or not all(isinstance(key, str) for key in response):
        raise ValueError(f"Human step {request.step_id!r} must receive a JSON object keyed by artifact ID")
    outputs = dict(response)
    expected = set(output_ids)
    actual = set(outputs)
    if actual != expected:
        raise ValueError(
            f"Human step {request.step_id!r} outputs must match exactly: "
            f"expected {sorted(expected)}, got {sorted(actual)}"
        )
    return outputs


def _checkpoint_human_response(
    checkpoint: ExecutionCheckpoint,
    request: HumanRequestSpec,
    response: object,
) -> ExecutionCheckpoint:
    if request.step_id in checkpoint.completed_step_ids:
        raise ValueError(f"Human step {request.step_id!r} is already completed")
    outputs = _human_response_outputs(request, response)
    collisions = set(outputs) & checkpoint.values.keys()
    if collisions:
        raise ValueError(f"Human step {request.step_id!r} would replace materialized artifacts: {sorted(collisions)}")
    values = dict(checkpoint.values)
    values.update(outputs)
    return ExecutionCheckpoint(
        values=values,
        completed_step_ids=tuple(sorted((*checkpoint.completed_step_ids, request.step_id))),
        completed_selection_ids=checkpoint.completed_selection_ids,
    )


def _job_store() -> JobStore:
    return JobStore(_WORKSPACE_DIR / _JOB_STORE_RELATIVE_PATH)


async def _read_flow_source(flow_path: str) -> str:
    workspace = await anyio.Path(str(_WORKSPACE_DIR)).resolve()
    candidate = anyio.Path(flow_path)
    if candidate.is_absolute():
        raise ValueError("flow_path must be relative to the workspace")
    candidate = workspace / flow_path
    resolved = await candidate.resolve()
    flows_dir = await (workspace / "flows").resolve()
    if not Path(str(resolved)).is_relative_to(Path(str(flows_dir))):
        raise ValueError("flow_path must stay inside the workspace flows directory")
    if resolved.suffix != ".workflow":
        raise ValueError("flow_path must name a .workflow file")
    return await resolved.read_text(encoding="utf-8")


def _resource_payload(context: CompletionContext) -> dict[str, list[str]]:
    return {grant.resource_id: list(grant.instance_ids) for grant in context.dispatch.resource_lease.grants}


async def _run_program(invocation: ProgramInvocation) -> str:
    """Execute one already-resolved Program invocation without a shell."""

    workspace = await anyio.Path(_WORKSPACE_DIR).resolve()
    executable = anyio.Path(invocation.argv[0])
    if not executable.is_absolute():
        if invocation.cwd is None:
            raise ValueError("relative Program executable requires an explicit working directory")
        executable = anyio.Path(invocation.cwd) / invocation.argv[0]
    resolved_executable = await executable.resolve()
    if not Path(str(resolved_executable)).is_relative_to(Path(str(workspace))):
        raise ValueError("program_path must resolve inside the workspace")

    with anyio.fail_after(_PROGRAM_TIMEOUT_SECONDS):
        completed = await anyio.run_process(
            invocation.argv,
            input=invocation.stdin.encode("utf-8"),
            cwd=invocation.cwd,
            check=False,
        )
    stdout = completed.stdout.decode("utf-8", errors="replace")
    stderr = completed.stderr.decode("utf-8", errors="replace")
    if completed.returncode != 0:
        output_tail = (stderr or stdout)[-300:].strip()
        raise RuntimeError(f"Program {invocation.name!r} exited with code {completed.returncode}: {output_tail}")
    return stdout.rstrip("\r\n")


async def _load_step_tools() -> ToolRegistry:
    global _STEP_TOOLS_SOURCE

    async with _STEP_TOOLS_LOAD_LOCK:
        if _STEP_TOOLS_SOURCE is None:
            _STEP_TOOLS_SOURCE = await ToolRegistry.load(
                _WORKSPACE_DIR / "tools",
                session_id=_STEP_TOOL_SESSION_ID,
            )
        else:
            await _STEP_TOOLS_SOURCE.refresh()

        excluded_tools = _WORKFLOW_LAUNCHERS | _NESTED_TURN_TOOLS
        tools = {name: tool for name, tool in _STEP_TOOLS_SOURCE.tools.items() if name not in excluded_tools}
        funcs = {name: func for name in tools if (func := _STEP_TOOLS_SOURCE.get(name)) is not None}
        return _StepToolRegistry(
            files={
                "__fusion_flow_step_tools__": FileEntry(
                    file_hash="",
                    tools=tools,
                    funcs=funcs,
                )
            }
        )


def _build_human_preparer_tools(source: ToolRegistry) -> ToolRegistry:
    """Expose only workspace-confined, read-only tools to a Human preparer."""

    source_read = source.get("read")
    if source_read is None:
        return _StepToolRegistry()

    async def read(file_path: str, offset: int = 0, limit: int = 0) -> str:
        """Read one text file that resolves inside the Haitun workspace.

        Args:
            file_path: Workspace-relative path, or an absolute path inside the workspace.
            offset: Zero-based line offset.
            limit: Maximum number of lines, or zero for the remainder.

        Returns:
            The requested file content.
        """

        workspace = await anyio.Path(_WORKSPACE_DIR).resolve()
        candidate = anyio.Path(file_path)
        if not candidate.is_absolute():
            candidate = workspace / candidate
        resolved = await candidate.resolve()
        if not Path(str(resolved)).is_relative_to(Path(str(workspace))):
            raise ValueError("Human preparer may read only files inside the workspace")
        return cast(str, await source_read(str(resolved), offset, limit))

    metadata = ToolFunction.from_callable(read)
    if metadata.name not in _HUMAN_PREPARER_TOOLS:
        raise AssertionError(f"unexpected Human preparer tool name: {metadata.name}")
    return _StepToolRegistry(
        files={
            "__fusion_flow_human_preparer_tools__": FileEntry(
                file_hash="",
                tools={metadata.name: metadata},
                funcs={metadata.name: read},
            )
        }
    )


async def _create_step_agent(
    ai_socket: str,
    tool_registry: ToolRegistry,
    *,
    system_prompt: str = _STEP_SYSTEM_PROMPT,
) -> tuple[SessionAgent, Conversation]:
    conversation = Conversation(
        messages=[{"role": "system", "content": system_prompt}],
    )
    agent = SessionAgent(
        ai_client=AiClient(ai_socket),
        conversation=conversation,
        schedule_registry=_StepScheduleRegistry(),
        tool_registry=tool_registry,
    )
    return agent, conversation


async def _complete_step_agent(
    agent: SessionAgent,
    conversation: Conversation,
    message: str,
) -> str:
    async with aclosing(agent.run({"role": "user", "content": message})) as chunks:
        async for _ in chunks:
            pass

    if not conversation.messages:
        raise RuntimeError("step agent produced no final assistant text")
    final = conversation.messages[-1]
    content = final.get("content")
    if (
        final.get("role") != "assistant"
        or final.get("tool_calls")
        or not isinstance(content, str)
        or not content.strip()
    ):
        raise RuntimeError("step agent produced no final assistant text")
    return content


async def _complete_agent_step(
    prompt: str,
    context: CompletionContext,
    *,
    ai_socket: str,
    tool_registry: ToolRegistry,
) -> dict[str, object]:
    agent, conversation = await _create_step_agent(ai_socket, tool_registry)
    message = (
        "Execute exactly one assigned FusionFlow step. Do not start another workflow.\n"
        f"Step: {context.step_id}\n"
        f"Executor: {context.executor_id}\n"
        f"Reserved resources: {json.dumps(_resource_payload(context), ensure_ascii=False, sort_keys=True)}\n"
        f"Required output keys: {json.dumps(context.output_ids, ensure_ascii=False)}\n"
        f"{prompt}\n"
        "Respond with exactly one JSON object keyed by exactly those output keys, "
        "with no surrounding prose or Markdown."
    )
    response = await _complete_step_agent(agent, conversation, message)
    return _parse_mapping(response, label=f"response for step {context.step_id!r}")


async def _prepare_human_step(
    prompt: str,
    context: CompletionContext,
    *,
    ai_socket: str,
    tool_registry: ToolRegistry,
) -> str:
    agent, conversation = await _create_step_agent(
        ai_socket,
        tool_registry,
        system_prompt=_HUMAN_PREPARER_SYSTEM_PROMPT,
    )
    message = (
        "Prepare one request for the person responsible for this Human step.\n"
        f"Step: {context.step_id}\n"
        f"Executor: {context.executor_id}\n"
        f"Reserved resources: {json.dumps(_resource_payload(context), ensure_ascii=False, sort_keys=True)}\n"
        f"Output artifact IDs: {json.dumps(context.output_ids, ensure_ascii=False)}\n"
        f"{prompt}\n"
        "Use options for a bounded choice or approval; omit options for open-ended input. "
        "The existing clarify tool automatically permits a free-text Other answer when options are present. "
        "Respond with exactly one JSON object with exactly these keys: "
        '{"question":"...","options":[],"recommended":0,"default":""}. '
        "options may contain at most four strings; recommended is a 1-based option index or 0; "
        "default is only for open-ended input. Do not add Markdown or prose."
    )
    response = await _complete_step_agent(agent, conversation, message)
    return _prepared_question_json(_parse_prepared_human_question(response))


def _human_request_payload(run_id: str, request: HumanRequestSpec) -> str:
    return json.dumps(
        {
            _HUMAN_CONTROL_KEY: {
                "status": "waiting_for_human",
                "run_id": run_id,
                "request": {
                    "request_id": request.request_id,
                    "step_id": request.step_id,
                    "question": request.question,
                    "options": list(request.options),
                    "recommended": request.recommended,
                    "default": request.default,
                    "output_artifact_ids": list(request.output_artifact_ids),
                },
            },
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _collect_human_requests(error: BaseException) -> list[HumanRequestSpec]:
    if isinstance(error, _HumanInputRequiredError):
        return [error.request]
    if isinstance(error, BaseExceptionGroup):
        return [request for nested in error.exceptions for request in _collect_human_requests(nested)]
    return []


def _is_cancellation(error: BaseException) -> bool:
    cancelled = anyio.get_cancelled_exc_class()
    if isinstance(error, cancelled):
        return True
    return isinstance(error, BaseExceptionGroup) and all(_is_cancellation(nested) for nested in error.exceptions)


async def _execute_persisted_run(
    source: str,
    run: HumanWorkflowRun,
    lease: RunLease,
    *,
    ai_socket: str,
) -> str:
    if run.prepared_request is not None:
        raise ValueError("a Human response must be checkpointed before execution resumes")
    run_state = run
    step_tools: ToolRegistry | None = None
    human_tools: ToolRegistry | None = None
    step_tools_lock = anyio.Lock()
    human_gate = anyio.Lock()
    human_wait_started = anyio.Event()

    async def get_step_tools() -> ToolRegistry:
        nonlocal step_tools
        if step_tools is None:
            async with step_tools_lock:
                if step_tools is None:
                    step_tools = await _load_step_tools()
        return step_tools

    async def get_human_tools() -> ToolRegistry:
        nonlocal human_tools
        if human_tools is None:
            human_tools = _build_human_preparer_tools(await get_step_tools())
        return human_tools

    async def complete(prompt: str, context: CompletionContext) -> dict[str, object]:
        return await _complete_agent_step(
            prompt,
            context,
            ai_socket=ai_socket,
            tool_registry=await get_step_tools(),
        )

    async def prepare_human(prompt: str, context: CompletionContext) -> str:
        await human_gate.acquire()
        owns_human_gate = True
        try:
            if human_wait_started.is_set():
                human_gate.release()
                owns_human_gate = False
                await anyio.sleep_forever()
                raise AssertionError("sleep_forever returned unexpectedly")
            return await _prepare_human_step(
                prompt,
                context,
                ai_socket=ai_socket,
                tool_registry=await get_human_tools(),
            )
        except BaseException:
            if owns_human_gate:
                human_gate.release()
            raise

    async def request_human(prepared: str, context: CompletionContext) -> object:
        try:
            question = _parse_prepared_human_question(prepared)
            request = HumanRequestSpec.create(
                step_id=context.step_id,
                question=question.question,
                output_artifact_ids=context.output_ids,
                options=question.options,
                recommended=question.recommended,
                default=question.default,
            )
            human_wait_started.set()
            raise _HumanInputRequiredError(request)
        finally:
            if human_gate.locked():
                human_gate.release()

    async def observe_checkpoint(checkpoint: ExecutionCheckpoint) -> None:
        nonlocal run_state
        updated = replace(
            run_state,
            checkpoint=checkpoint,
        )
        with anyio.CancelScope(shield=True):
            await lease.save(updated)
        run_state = updated

    human_requests: list[HumanRequestSpec] = []
    outputs: dict[str, object] | None = None
    try:
        try:
            outputs = await _execute_workflow(
                source,
                inputs=run.inputs,
                contextual_complete=complete,
                resource_capacities=run.resource_capacities,
                strict_executors=True,
                supported_executor_kinds=("Agent", "Human", "Program"),
                work_dir=_WORKSPACE_DIR,
                run_program=_run_program,
                contextual_prepare_human_instruction=prepare_human,
                contextual_request_human=request_human,
                checkpoint=run.checkpoint,
                checkpoint_observer=observe_checkpoint,
            )
        except* _HumanInputRequiredError as error_group:
            human_requests.extend(_collect_human_requests(error_group))
    except BaseException as error:
        if _is_cancellation(error):
            recoverable = replace(
                run_state,
                status="running",
                prepared_request=None,
            )
        else:
            details = str(error).strip() or type(error).__name__
            recoverable = replace(
                run_state,
                status="failed",
                prepared_request=None,
                error=details,
            )
        try:
            with anyio.CancelScope(shield=True):
                await lease.save(recoverable)
        except Exception as persistence_error:
            error.add_note(f"also failed to persist terminal run state: {persistence_error}")
        raise

    if human_requests:
        request = min(
            human_requests,
            key=lambda item: (item.step_id, item.request_id),
        )
        waiting = replace(
            run_state,
            status="waiting_for_human",
            prepared_request=request,
        )
        with anyio.CancelScope(shield=True):
            await lease.save(waiting)
        return _human_request_payload(waiting.run_id, request)

    if outputs is None:
        raise AssertionError("workflow execution produced neither outputs nor a Human request")
    completed = replace(
        run_state,
        status="completed",
        prepared_request=None,
        outputs=outputs,
    )
    with anyio.CancelScope(shield=True):
        await lease.save(completed)
    return json.dumps(outputs, ensure_ascii=False, sort_keys=True)


async def run_flow(
    flow_path: str,
    inputs_json: str = "{}",
    resource_capacities_json: str = "",
) -> str:
    """Start one G4 workflow and return outputs or a persisted Human request.

    Args:
        flow_path: Workspace-relative path to a UTF-8 ``.workflow`` file.
        inputs_json: JSON object keyed by the workflow's input artifact IDs.
        resource_capacities_json: Optional JSON object mapping resource IDs to
            positive counts or concrete instance-ID arrays.

    Returns:
        A JSON object keyed by output artifact IDs, or a
        reserved ``$fusion_flow/control`` envelope whose request fields are
        passed through ``clarify``.
    """

    ai_socket = current_tool_ai_socket()
    if ai_socket is None:
        raise RuntimeError("run_flow must be called by a psi-agent Session")

    source = await _read_flow_source(flow_path)
    inputs = _parse_mapping(inputs_json, label="inputs_json")
    resource_capacities = _parse_resource_capacities(resource_capacities_json)
    compiled = compile_workflow(source, strict_executors=True)
    has_human = any(compiled.executor_kinds[step.executor_id] == "Human" for step in compiled.graph.steps)
    if has_human:
        store = _job_store()
        run = await store.create(
            flow_path=flow_path,
            flow_source=source,
            inputs=inputs,
            resource_capacities=resource_capacities,
            checkpoint=ExecutionCheckpoint(values=inputs),
        )
        async with store.acquire(run.run_id) as lease:
            return await _execute_persisted_run(
                source,
                await lease.load(),
                lease,
                ai_socket=ai_socket,
            )

    step_tools: ToolRegistry | None = None
    step_tools_lock = anyio.Lock()

    async def get_step_tools() -> ToolRegistry:
        nonlocal step_tools
        if step_tools is None:
            async with step_tools_lock:
                if step_tools is None:
                    step_tools = await _load_step_tools()
        return step_tools

    async def complete(prompt: str, context: CompletionContext) -> dict[str, object]:
        return await _complete_agent_step(
            prompt,
            context,
            ai_socket=ai_socket,
            tool_registry=await get_step_tools(),
        )

    outputs = await _execute_workflow(
        source,
        inputs=inputs,
        contextual_complete=complete,
        resource_capacities=resource_capacities,
        strict_executors=True,
        supported_executor_kinds=("Agent", "Program"),
        work_dir=_WORKSPACE_DIR,
        run_program=_run_program,
    )
    return json.dumps(outputs, ensure_ascii=False, sort_keys=True)


async def run_flow_resume(
    run_id: str,
    request_id: str,
    human_response_json: str,
) -> str:
    """Resume one persisted Human Step with a choice, free text, or JSON value.

    Args:
        run_id: Opaque run ID returned by ``run_flow``.
        request_id: Opaque Human request ID returned by the latest wait.
        human_response_json: The person's response encoded as any valid JSON
            value. For multiple output artifacts, use an object keyed exactly
            by those artifact IDs.

    Returns:
        The final output Artifact mapping, or the next
        reserved ``$fusion_flow/control`` Human-wait envelope.
    """

    ai_socket = current_tool_ai_socket()
    if ai_socket is None:
        raise RuntimeError("run_flow_resume must be called by a psi-agent Session")
    response = _parse_human_response(human_response_json)
    store = _job_store()

    async with store.acquire(run_id) as lease:
        run = await lease.load()
        if run.status == "completed":
            if request_id not in run.human_responses:
                raise ValueError(f"request_id {request_id!r} does not belong to completed run {run_id!r}")
            if not _json_values_equal(run.human_responses[request_id], response):
                raise ValueError(f"request_id {request_id!r} already has a different response")
            if run.outputs is None:
                raise AssertionError("completed run has no outputs")
            return json.dumps(run.outputs, ensure_ascii=False, sort_keys=True)
        if run.status in {"failed", "cancelled"}:
            details = "" if run.error is None else f": {run.error}"
            raise ValueError(f"FusionFlow run {run_id!r} is {run.status}{details}")

        source = await _read_flow_source(run.flow_path)
        digest = hashlib.sha256(source.encode()).hexdigest()
        if digest != run.flow_source_digest:
            failed = replace(
                run,
                status="failed",
                prepared_request=None,
                error="workflow source changed after the Human request was prepared",
            )
            with anyio.CancelScope(shield=True):
                await lease.save(failed)
            raise ValueError(f"workflow source changed for FusionFlow run {run_id!r}")

        if run.status == "running":
            if request_id not in run.human_responses:
                raise ValueError(f"FusionFlow run {run_id!r} is not waiting for Human input")
            if not _json_values_equal(run.human_responses[request_id], response):
                raise ValueError(f"request_id {request_id!r} already has a different response")
            return await _execute_persisted_run(
                source,
                run,
                lease,
                ai_socket=ai_socket,
            )

        if request_id in run.human_responses:
            if not _json_values_equal(run.human_responses[request_id], response):
                raise ValueError(f"request_id {request_id!r} already has a different response")
            if run.prepared_request is None:
                raise ValueError(f"FusionFlow run {run_id!r} is not waiting for Human input")
            return _human_request_payload(run_id, run.prepared_request)

        if run.prepared_request is None:
            raise ValueError(f"FusionFlow run {run_id!r} is not waiting for Human input")
        if run.prepared_request.request_id != request_id:
            raise ValueError(f"request_id does not match the active Human request for run {run_id!r}")
        if run.checkpoint is None:
            raise ValueError(f"FusionFlow run {run_id!r} has no resumable checkpoint")
        checkpoint = _checkpoint_human_response(
            run.checkpoint,
            run.prepared_request,
            response,
        )
        responses = dict(run.human_responses)
        responses[request_id] = response
        resumed = replace(
            run,
            status="running",
            checkpoint=checkpoint,
            prepared_request=None,
            human_responses=responses,
        )
        with anyio.CancelScope(shield=True):
            await lease.save(resumed)

        return await _execute_persisted_run(
            source,
            resumed,
            lease,
            ai_socket=ai_socket,
        )
