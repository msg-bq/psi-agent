from __future__ import annotations

import importlib.util
import inspect
import json
import os
import socket
import subprocess
import sys
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any, cast

import anyio
import pytest
from aiohttp import web

from psi_agent.session.tool_registry import ToolFunction

_SKILL_DIR = os.path.dirname(os.path.dirname(__file__))
_WORKSPACE_DIR = os.path.dirname(os.path.dirname(_SKILL_DIR))
_RUNNER_PATH = os.path.join(_WORKSPACE_DIR, "tools", "run_flow.py")


def _load_module(name: str, path: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return cast("Any", module)


run_flow_tool = _load_module("fusion_flow_next_run_flow_tool", _RUNNER_PATH)


def test_frozen_executable_loads_run_flow_and_executes_worker(tmp_path: Any) -> None:
    executable_value = os.environ.get("FROZEN_EXECUTABLE", "").strip()
    if not executable_value:
        pytest.skip("FROZEN_EXECUTABLE is only set by frozen-build smoke jobs")

    root = os.fspath(tmp_path)
    state_dir = os.path.join(root, "state")
    runs_dir = os.path.join(root, "runs")
    work_dir = os.path.join(root, "work")
    os.makedirs(state_dir)
    os.makedirs(runs_dir)
    os.makedirs(work_dir)
    run_token = f"g4-{'1' * 32}"
    state_path = os.path.join(state_dir, f"{run_token}.json")
    state = {
        "run_token": run_token,
        "attempt_id": "2" * 32,
        "run_id": "frozen-smoke",
        "resume_run_id": "",
        "run_dir": os.path.join(runs_dir, "frozen-smoke"),
        "runs_dir": runs_dir,
        "source": """
const smoke: Workflow;
const value: Artifact;
workflow smoke {
    input_workflow(smoke) == [value];
    output_workflow(smoke) == [value];
}
""",
        "inputs": {"value": "frozen-ok"},
        "work_dir": work_dir,
        "workspace": _WORKSPACE_DIR,
        "ai_socket": "unused-by-empty-plan",
        "progress_offset": 0,
        "log_path": os.path.join(state_dir, f"{run_token}.log"),
    }
    with open(state_path, "w", encoding="utf-8") as stream:
        json.dump(state, stream)

    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["FLOW_NEXT_RUN_STATE_DIR"] = state_dir
    completed = subprocess.run(
        [
            os.path.abspath(executable_value),
            "workspace-tool-worker",
            _RUNNER_PATH,
            state_path,
        ],
        cwd=os.path.dirname(os.path.dirname(_WORKSPACE_DIR)),
        env=environment,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )

    log_path = os.fspath(state["log_path"])
    log = ""
    if os.path.isfile(log_path):
        with open(log_path, encoding="utf-8") as stream:
            log = stream.read()
    assert completed.returncode == 0, (
        f"frozen worker failed with exit code {completed.returncode}\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}\n"
        f"worker log:\n{log}"
    )
    with open(
        os.path.join(state_dir, f"{run_token}.result.json"),
        encoding="utf-8",
    ) as stream:
        terminal = json.load(stream)
    assert terminal["meta"]["status"] == "ok"
    assert terminal["outputs"] == {"value": "frozen-ok"}


@pytest.mark.anyio
async def test_skill_dir_falls_back_to_the_fusion_flow_replacement(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    workspace = anyio.Path(str(tmp_path)) / "workspace"
    skills = workspace / "skills"
    await (skills / "fusion-flow-next").mkdir(parents=True)
    replacement = skills / "fusion-flow"
    await (replacement / "examples").mkdir(parents=True)
    await (replacement / "fusion_flow_next").mkdir()
    await (replacement / "examples" / "run_workflow.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(run_flow_tool, "_WORKSPACE_DIR", str(workspace))

    assert run_flow_tool._resolve_skill_dir() == str(replacement)


_AGENT_WORKFLOW = """
const review: Workflow;
const request: Artifact;
const result: Artifact;
const review_step: Step;
const review_name: StepName;
const review_instruction: Instruction;
const reviewer: Agent;

workflow review {
    input_workflow(review) == [request];
    output_workflow(review) == [result];
    step_name(review_step) == review_name;
    step_instruction(review_step) == review_instruction;
    step_executor(review_step) == reviewer;
    consumes(review_step) == [request];
    produces(review_step) == [result];
}
"""

_TWO_INPUT_WORKFLOW = """
const merge: Workflow;
const left: Artifact;
const right: Artifact;
const result: Artifact;
const merge_step: Step;
const merge_name: StepName;
const merge_instruction: Instruction;
const merger: Agent;

workflow merge {
    input_workflow(merge) == [left, right];
    output_workflow(merge) == [result];
    step_name(merge_step) == merge_name;
    step_instruction(merge_step) == merge_instruction;
    step_executor(merge_step) == merger;
    consumes(merge_step) == [left, right];
    produces(merge_step) == [result];
}
"""

_FANOUT_WORKFLOW = """
const review: Workflow;
const request: Artifact;
const security_findings: Artifact;
const performance_score: Artifact;
const report: Artifact;
const security_step: Step;
const performance_step: Step;
const synthesis_step: Step;
const security_name: StepName;
const performance_name: StepName;
const synthesis_name: StepName;
const security_instruction: Instruction;
const performance_instruction: Instruction;
const synthesis_instruction: Instruction;
const security_agent: Agent;
const performance_agent: Agent;
const synthesis_agent: Agent;

workflow review {
    input_workflow(review) == [request];
    output_workflow(review) == [report];

    step_name(security_step) == security_name;
    step_instruction(security_step) == security_instruction;
    step_executor(security_step) == security_agent;
    consumes(security_step) == [request];
    produces(security_step) == [security_findings];

    step_name(performance_step) == performance_name;
    step_instruction(performance_step) == performance_instruction;
    step_executor(performance_step) == performance_agent;
    consumes(performance_step) == [request];
    produces(performance_step) == [performance_score];

    step_name(synthesis_step) == synthesis_name;
    step_instruction(synthesis_step) == synthesis_instruction;
    step_executor(synthesis_step) == synthesis_agent;
    consumes(synthesis_step) == [security_findings, performance_score];
    produces(synthesis_step) == [report];

    max_concurrency(review) == 2;
}
"""


def _executor_workflow(executor_concept: str) -> str:
    return f"""
const dispatch: Workflow;
const request: Artifact;
const result: Artifact;
const dispatch_step: Step;
const dispatch_name: StepName;
const dispatch_instruction: Instruction;
const worker: {executor_concept};

workflow dispatch {{
    input_workflow(dispatch) == [request];
    output_workflow(dispatch) == [result];
    step_name(dispatch_step) == dispatch_name;
    step_instruction(dispatch_step) == dispatch_instruction;
    step_executor(dispatch_step) == worker;
    consumes(dispatch_step) == [request];
    produces(dispatch_step) == [result];
}}
"""


def test_module_exposes_only_run_flow_as_a_public_async_tool() -> None:
    public_async = {
        name
        for name, member in inspect.getmembers(run_flow_tool, inspect.iscoroutinefunction)
        if not name.startswith("_")
    }

    assert public_async == {"run_flow"}


def test_run_flow_has_the_workspace_tool_contract() -> None:
    signature = inspect.signature(run_flow_tool.run_flow)

    assert list(signature.parameters) == [
        "action",
        "flow_path",
        "inputs_json",
        "inputs_path",
        "run_token",
        "cwd",
        "window_seconds",
        "resume_run_id",
    ]
    assert signature.parameters["action"].default is inspect.Parameter.empty
    assert signature.parameters["flow_path"].default == ""
    assert signature.parameters["inputs_json"].default == ""
    assert signature.parameters["inputs_path"].default == ""
    assert signature.parameters["run_token"].default == ""
    assert signature.parameters["cwd"].default == ""
    assert signature.parameters["window_seconds"].default == 60.0
    assert signature.parameters["resume_run_id"].default == ""
    assert signature.return_annotation in (str, "str")


def test_run_flow_builds_a_valid_workspace_tool_schema() -> None:
    tool = ToolFunction.from_callable(run_flow_tool.run_flow)

    assert tool.name == "run_flow"
    assert tool.parameters["required"] == ["action"]
    assert set(tool.parameters["properties"]) == {
        "action",
        "flow_path",
        "inputs_json",
        "inputs_path",
        "run_token",
        "cwd",
        "window_seconds",
        "resume_run_id",
    }


@pytest.mark.parametrize(
    ("output_ids", "text", "expected"),
    [
        (("answer",), "plain text stays plain", {"answer": "plain text stays plain"}),
        (
            ("summary", "verdict"),
            '{"summary":"concise","verdict":{"approved":true}}',
            {"summary": "concise", "verdict": {"approved": True}},
        ),
        ((), "", {}),
        ((), "   \n", {}),
    ],
)
def test_normalize_step_output_accepts_each_supported_output_shape(
    output_ids: tuple[str, ...],
    text: str,
    expected: dict[str, object],
) -> None:
    assert run_flow_tool._normalize_step_output("review_step", output_ids, text) == expected


@pytest.mark.parametrize(
    ("output_ids", "text", "message"),
    [
        ((), "unexpected", "produces no artifacts"),
        (("left", "right"), "not json", "JSON object"),
        (("left", "right"), '["left", "right"]', "JSON object"),
        (("left", "right"), '{"left":"only"}', "match exactly"),
        (("left", "right"), '{"left":"ok","right":"ok","extra":"no"}', "match exactly"),
    ],
)
def test_normalize_step_output_rejects_ambiguous_or_mismatched_results(
    output_ids: tuple[str, ...],
    text: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        run_flow_tool._normalize_step_output("review_step", output_ids, text)


def test_preflight_builds_a_plan_for_exact_named_inputs() -> None:
    compiled, plan = run_flow_tool._preflight(
        _TWO_INPUT_WORKFLOW,
        {"left": "first", "right": "second"},
    )

    assert compiled.graph.workflow_id == "merge"
    assert plan.workflow_id == "merge"
    assert {artifact.artifact_id for artifact in compiled.graph.artifacts if artifact.is_input} == {
        "left",
        "right",
    }


@pytest.mark.parametrize(
    "inputs",
    [
        {"left": "first"},
        {"left": "first", "right": "second", "extra": "third"},
        {"request": "wrong input name"},
    ],
)
def test_preflight_requires_inputs_to_match_the_graph_exactly(inputs: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="inputs must match exactly"):
        run_flow_tool._preflight(_TWO_INPUT_WORKFLOW, inputs)


def test_preflight_accepts_an_agent_executor() -> None:
    compiled, plan = run_flow_tool._preflight(_AGENT_WORKFLOW, {"request": "review this"})

    assert plan.workflow_id == compiled.graph.workflow_id == "review"
    assert compiled.executor_kinds == {"reviewer": "Agent"}


@pytest.mark.parametrize("executor_concept", ["Program", "Human"])
def test_preflight_rejects_executor_kinds_without_runtime_boundaries(executor_concept: str) -> None:
    with pytest.raises(ValueError, match=rf"{executor_concept}.*not supported|unsupported.*{executor_concept}"):
        run_flow_tool._preflight(
            _executor_workflow(executor_concept),
            {"request": "do the work"},
        )


@pytest.mark.parametrize(
    "source",
    [
        "this is not FusionFlow",
        "workflow missing_brace {",
        _AGENT_WORKFLOW.replace("produces(review_step) == [result];", "made_up(review_step) == [result];"),
    ],
)
def test_preflight_rejects_invalid_or_unexecutable_source(source: str) -> None:
    with pytest.raises(ValueError):
        run_flow_tool._preflight(source, {"request": "review this"})


def test_preflight_rejects_artifact_ids_that_cannot_be_persisted_safely() -> None:
    source = _AGENT_WORKFLOW.replace("request", '"./request"')

    with pytest.raises(ValueError, match=r"Artifact ID.*runtime-safe"):
        run_flow_tool._preflight(source, {"./request": "review this"})


@pytest.mark.anyio
async def test_start_preflights_g4_and_persists_worker_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    root = anyio.Path(str(tmp_path))
    source_path = root / "review.g4"
    state_dir = root / "state"
    await source_path.write_text(_AGENT_WORKFLOW, encoding="utf-8")
    monkeypatch.setenv("FLOW_NEXT_RUN_STATE_DIR", str(state_dir))
    monkeypatch.setattr(run_flow_tool, "_resolve_ai_socket", lambda: "http://127.0.0.1:9999")

    async def spawn_worker(state_path: anyio.Path, *, cwd: str) -> int:
        assert state_path.parent == state_dir
        assert cwd == str(root)
        return 4242

    monkeypatch.setattr(run_flow_tool, "_spawn_worker", spawn_worker)

    started = json.loads(
        await run_flow_tool.run_flow(
            "start",
            flow_path=str(source_path),
            inputs_json='{"request":"review this"}',
            cwd=str(root),
        )
    )
    state = await run_flow_tool._read_json_object(run_flow_tool._state_path(started["run_token"]))

    assert started["ok"] is True
    assert started["pid"] == 4242
    assert started["resumed"] is False
    assert state is not None
    assert state["source"] == _AGENT_WORKFLOW
    assert state["inputs"] == {"request": "review this"}
    assert state["ai_socket"] == "http://127.0.0.1:9999"
    assert state["run_id"] == started["run_id"]
    assert state["attempt_id"] == started["attempt_id"]
    lock_dir = anyio.Path(str(state["lock_dir"]))
    assert await lock_dir.is_dir()
    assert lock_dir == run_flow_tool._run_lock_path(str(root / "runs"), started["run_id"])
    assert state_dir not in lock_dir.parents
    assert not await anyio.Path(str(started["run_dir"])).exists()
    assert await run_flow_tool._release_run_lock(
        lock_dir,
        expected_token=started["run_token"],
    )


@pytest.mark.anyio
async def test_run_lock_is_shared_across_state_directories(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    root = anyio.Path(str(tmp_path))
    runs_dir = str(root / "runs")
    run_id = "shared-run"
    first_token = run_flow_tool._make_run_token()
    monkeypatch.setenv("FLOW_NEXT_RUN_STATE_DIR", str(root / "state-a"))
    first_path = run_flow_tool._run_lock_path(runs_dir, run_id)
    lock_dir = await run_flow_tool._acquire_run_lock(runs_dir, run_id, first_token)

    monkeypatch.setenv("FLOW_NEXT_RUN_STATE_DIR", str(root / "state-b"))
    second_path = run_flow_tool._run_lock_path(runs_dir, run_id)
    with pytest.raises(RuntimeError, match="already locked"):
        await run_flow_tool._acquire_run_lock(
            runs_dir,
            run_id,
            run_flow_tool._make_run_token(),
        )

    assert first_path == second_path == lock_dir
    assert await run_flow_tool._release_run_lock(lock_dir, expected_token=first_token)


@pytest.mark.anyio
async def test_start_rejects_the_legacy_typescript_format(tmp_path: Any) -> None:
    source_path = anyio.Path(str(tmp_path)) / "legacy.flow.ts"
    await source_path.write_text("export {}", encoding="utf-8")

    result = json.loads(await run_flow_tool.run_flow("start", flow_path=str(source_path)))

    assert result["ok"] is False
    assert result["error_type"] == "ValueError"
    assert "G4" in result["message"]
    assert "TypeScript" in result["message"]


def test_relative_ai_socket_is_resolved_before_worker_cwd_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    root = os.path.abspath(str(tmp_path))
    monkeypatch.chdir(root)
    monkeypatch.setattr(run_flow_tool, "current_tool_ai_socket", lambda: "./ai.sock")

    assert run_flow_tool._resolve_ai_socket() == os.path.join(root, "ai.sock")


def test_relative_state_directory_is_resolved_before_worker_cwd_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    root = os.path.abspath(str(tmp_path))
    monkeypatch.chdir(root)
    monkeypatch.setenv("FLOW_NEXT_RUN_STATE_DIR", "relative-state")

    assert run_flow_tool._state_dir() == anyio.Path(root) / "relative-state"
    assert run_flow_tool._state_path(run_flow_tool._make_run_token()).is_absolute()


def test_context_encoding_preserves_json_types() -> None:
    assert run_flow_tool._context_text(123) == "123"
    assert run_flow_tool._context_text("123") == '"123"'
    assert run_flow_tool._context_text(True) == "true"
    assert run_flow_tool._context_text("true") == '"true"'
    assert run_flow_tool._context_value('{"nested":[1,true,null]}') == {"nested": [1, True, None]}


def test_windows_pid_probe_queries_without_signalling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object]] = []

    def open_process(access: int, inherit: bool, pid: int) -> int:
        calls.append(("open", (access, inherit, pid)))
        return 42

    def get_exit_code_process(handle: int, exit_code: Any) -> int:
        calls.append(("status", handle))
        exit_code._obj.value = run_flow_tool._STILL_ACTIVE
        return 1

    def close_handle(handle: int) -> int:
        calls.append(("close", handle))
        return 1

    monkeypatch.setattr(run_flow_tool.sys, "platform", "win32")
    monkeypatch.setattr(
        run_flow_tool,
        "_KERNEL32",
        SimpleNamespace(
            OpenProcess=open_process,
            GetExitCodeProcess=get_exit_code_process,
            CloseHandle=close_handle,
        ),
    )

    assert run_flow_tool._pid_alive(4242) is True
    assert calls == [
        (
            "open",
            (
                run_flow_tool._PROCESS_QUERY_LIMITED_INFORMATION,
                False,
                4242,
            ),
        ),
        ("status", 42),
        ("close", 42),
    ]


@pytest.mark.anyio
@pytest.mark.parametrize("pyinstaller", [True, False])
async def test_standalone_build_spawns_worker_with_error_log(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
    pyinstaller: bool,
) -> None:
    captured: dict[str, object] = {}

    class Process:
        pid = 4242

    async def open_process(argv: list[str], **kwargs: object) -> Process:
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        captured["stderr_name"] = str(getattr(kwargs["stderr"], "name", ""))
        return Process()

    monkeypatch.delenv("FLOW_NEXT_PYTHON", raising=False)
    monkeypatch.setenv("PARENT_SENTINEL", "preserved")
    monkeypatch.setattr(run_flow_tool, "is_standalone_executable", lambda: True)
    monkeypatch.setattr(run_flow_tool.sys, "frozen", pyinstaller, raising=False)
    monkeypatch.setattr(run_flow_tool.sys, "executable", "psi-agent.exe")
    monkeypatch.setattr(run_flow_tool.anyio, "open_process", open_process)
    root = anyio.Path(str(tmp_path))
    state_path = root / "state.json"
    log_path = root / "worker.log"
    await state_path.write_text(
        json.dumps({"log_path": str(log_path)}),
        encoding="utf-8",
    )

    pid = await run_flow_tool._spawn_worker(state_path, cwd=str(tmp_path))

    assert pid == 4242
    assert captured["argv"] == [
        "psi-agent.exe",
        "workspace-tool-worker",
        run_flow_tool._THIS_FILE,
        str(state_path),
    ]
    kwargs = cast(dict[str, object], captured["kwargs"])
    if pyinstaller:
        environment = cast(dict[str, str], kwargs["env"])
        assert environment["PARENT_SENTINEL"] == "preserved"
        assert environment["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    else:
        assert "env" not in kwargs
    assert captured["stderr_name"] == str(log_path)


@pytest.mark.anyio
async def test_relative_worker_python_is_resolved_before_cwd_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    root = str(tmp_path)
    captured: dict[str, object] = {}

    class Process:
        pid = 4242

    async def open_process(argv: list[str], **kwargs: object) -> Process:
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        captured["stderr_name"] = str(getattr(kwargs["stderr"], "name", ""))
        return Process()

    monkeypatch.chdir(root)
    monkeypatch.setenv("FLOW_NEXT_PYTHON", "./venv/python")
    monkeypatch.setattr(run_flow_tool.anyio, "open_process", open_process)
    state_path = anyio.Path(root) / "state.json"
    log_path = anyio.Path(root) / "worker.log"
    await state_path.write_text(
        json.dumps({"log_path": str(log_path)}),
        encoding="utf-8",
    )

    await run_flow_tool._spawn_worker(state_path, cwd=os.path.join(root, "work"))

    assert captured["argv"] == [
        os.path.join(root, "venv", "python"),
        run_flow_tool._THIS_FILE,
        "--worker",
        str(state_path),
    ]
    assert "env" not in cast(dict[str, object], captured["kwargs"])
    assert captured["stderr_name"] == str(log_path)


@pytest.mark.anyio
async def test_agent_step_uses_a_real_psi_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    root = anyio.Path(str(tmp_path))
    tools_dir = root / "tools"
    await tools_dir.mkdir()
    await (tools_dir / "echo.py").write_text(
        'async def echo(message: str) -> str:\n    """Return a message."""\n    return message\n',
        encoding="utf-8",
    )
    request_count = 0

    async def ai_handler(request: web.Request) -> web.StreamResponse:
        nonlocal request_count
        request_count += 1
        await request.json()
        response = web.StreamResponse(
            status=200,
            headers={"Content-Type": "text/event-stream"},
        )
        await response.prepare(request)
        if request_count == 1:
            chunks = [
                {
                    "id": "test",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": "I will read the file first."},
                            "finish_reason": None,
                        }
                    ],
                },
                {
                    "id": "test",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call-1",
                                        "type": "function",
                                        "function": {
                                            "name": "echo",
                                            "arguments": '{"message":"read"}',
                                        },
                                    }
                                ]
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                },
            ]
        else:
            chunks = [
                {
                    "id": "test",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": '{"approved": true}'},
                            "finish_reason": "stop",
                        }
                    ],
                }
            ]
        for chunk in chunks:
            await response.write(f"data: {json.dumps(chunk)}\n\n".encode())
        await response.write(b"data: [DONE]\n\n")
        return response

    app = web.Application()
    app.router.add_post("/chat/completions", ai_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    ai_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ai_listener.bind(("127.0.0.1", 0))
    ai_port = int(ai_listener.getsockname()[1])
    await web.SockSite(runner, ai_listener).start()

    def allocate_channel_socket() -> str:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.bind(("127.0.0.1", 0))
            port = int(listener.getsockname()[1])
        finally:
            listener.close()
        return f"http://127.0.0.1:{port}"

    monkeypatch.setattr(run_flow_tool, "_allocate_channel_socket", allocate_channel_socket)
    try:
        result = await run_flow_tool._invoke_agent_session(
            ai_socket=f"http://127.0.0.1:{ai_port}",
            workspace=str(root),
            session_id="g4-test-session",
            message="Do the assigned step.",
        )
    finally:
        await runner.cleanup()

    history = [
        json.loads(line)
        for line in (await (root / "histories" / "g4-test-session.jsonl").read_text(encoding="utf-8")).splitlines()
    ]
    assert request_count == 2
    assert any(message.get("content") == "I will read the file first." for message in history)
    assert result == '{"approved": true}'
    assert "timeout_seconds" not in inspect.signature(run_flow_tool._chat_session).parameters


@pytest.mark.anyio
async def test_agent_step_does_not_fall_back_to_an_unfinished_assistant_turn(tmp_path: Any) -> None:
    root = anyio.Path(str(tmp_path))
    histories = root / "histories"
    await histories.mkdir()
    await (histories / "unfinished.jsonl").write_text(
        '{"role":"assistant","content":"old preamble","tool_calls":[{"id":"call-1"}]}\n'
        '{"role":"tool","tool_call_id":"call-1","content":"done"}\n',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="final assistant text reply"):
        await run_flow_tool._final_assistant_reply(
            workspace=str(root),
            session_id="unfinished",
        )


@pytest.mark.anyio
async def test_execute_graph_persists_progress_bindings_and_final_outputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    compiled, plan = run_flow_tool._preflight(_AGENT_WORKFLOW, {"request": "review this"})
    calls: list[tuple[str, tuple[str, ...], dict[str, object]]] = []
    root = anyio.Path(str(tmp_path))
    monkeypatch.setattr(
        run_flow_tool.sys,
        "argv",
        ["psi-agent.exe", "workspace-tool-worker"],
    )

    async def complete(
        step: Any,
        output_ids: tuple[str, ...],
        inputs: Mapping[str, object],
    ) -> str:
        calls.append((step.step_id, output_ids, dict(inputs)))
        return "review complete"

    outputs = await run_flow_tool._execute_graph(
        source=_AGENT_WORKFLOW,
        compiled=compiled,
        plan=plan,
        inputs={"request": "review this"},
        runs_dir=str(root / "runs"),
        run_id="test-run",
        resume_run_id="",
        ai_socket="unused-by-stub",
        workspace=str(root),
        work_dir=str(root),
        complete_step=complete,
    )

    run_dir = root / "runs" / "test-run"
    assert outputs == {"result": "review complete"}
    assert calls == [("review_step", ("result",), {"request": "review this"})]
    assert json.loads(await (run_dir / "outputs.json").read_text(encoding="utf-8")) == outputs
    assert json.loads(await (run_dir / run_flow_tool._RUN_MARKER_NAME).read_text(encoding="utf-8")) == {
        "run_id": "test-run",
        "runner": run_flow_tool._RUN_MARKER_KIND,
        "version": run_flow_tool._RUN_MARKER_VERSION,
        "workflow_id": "review",
    }
    assert await (run_dir / "program.py").read_text(encoding="utf-8") == await anyio.Path(
        run_flow_tool._THIS_FILE
    ).read_text(encoding="utf-8")
    assert await (run_dir / "input" / "request.md").read_text(encoding="utf-8") == '"review this"'
    assert await (run_dir / "bindings" / "result.md").read_text(encoding="utf-8") == "review complete"
    assert json.loads(await (run_dir / "workflow-graph.json").read_text(encoding="utf-8"))["workflow_id"] == "review"
    assert json.loads(await (run_dir / "execution-plan.json").read_text(encoding="utf-8"))["workflow_id"] == "review"
    assert json.loads(await (run_dir / "meta.json").read_text(encoding="utf-8"))["status"] == "ok"

    progress = [
        json.loads(line)
        for line in (await (run_dir / "progress.jsonl").read_text(encoding="utf-8")).splitlines()
        if line.strip()
    ]
    assert [event["event"] for event in progress] == [
        "node_start",
        "node_end",
        "node_start",
        "node_end",
    ]
    assert progress[-1]["status"] == "ok"


@pytest.mark.anyio
async def test_execute_graph_runs_g4_fanout_fanin_with_typed_artifacts(tmp_path: Any) -> None:
    compiled, plan = run_flow_tool._preflight(
        _FANOUT_WORKFLOW,
        {"request": {"change": "review me"}},
    )
    root = anyio.Path(str(tmp_path))
    calls: dict[str, dict[str, object]] = {}

    async def complete(
        step: Any,
        output_ids: tuple[str, ...],
        inputs: Mapping[str, object],
    ) -> str:
        del output_ids
        calls[step.step_id] = dict(inputs)
        if step.step_id == "security_step":
            return '{"severity":"low","issues":[]}'
        if step.step_id == "performance_step":
            return "7"
        assert step.step_id == "synthesis_step"
        assert inputs == {
            "performance_score": 7,
            "security_findings": {"severity": "low", "issues": []},
        }
        return '{"report":{"approved":true,"score":7}}'

    outputs = await run_flow_tool._execute_graph(
        source=_FANOUT_WORKFLOW,
        compiled=compiled,
        plan=plan,
        inputs={"request": {"change": "review me"}},
        runs_dir=str(root / "runs"),
        run_id="fanout-fanin",
        resume_run_id="",
        ai_socket="unused-by-stub",
        workspace=str(root),
        work_dir=str(root),
        complete_step=complete,
    )

    assert set(calls) == {
        "security_step",
        "performance_step",
        "synthesis_step",
    }
    assert calls["security_step"] == {"request": {"change": "review me"}}
    assert calls["performance_step"] == {"request": {"change": "review me"}}
    assert outputs == {"report": {"approved": True, "score": 7}}
    run_dir = root / "runs" / "fanout-fanin"
    assert json.loads(await (run_dir / "outputs.json").read_text(encoding="utf-8")) == outputs
    assert (
        json.loads(await (run_dir / "workflow-graph.json").read_text(encoding="utf-8"))["policy"]["max_concurrency"]
        == 2
    )


@pytest.mark.anyio
async def test_resume_cache_distinguishes_numbers_from_strings(tmp_path: Any) -> None:
    root = anyio.Path(str(tmp_path))
    runs_dir = root / "runs"
    run_id = "typed-inputs"
    calls: list[object] = []

    async def complete(
        step: Any,
        output_ids: tuple[str, ...],
        inputs: Mapping[str, object],
    ) -> str:
        del step, output_ids
        calls.append(inputs["request"])
        return f"{type(inputs['request']).__name__}:{inputs['request']}"

    compiled, plan = run_flow_tool._preflight(_AGENT_WORKFLOW, {"request": 123})
    first = await run_flow_tool._execute_graph(
        source=_AGENT_WORKFLOW,
        compiled=compiled,
        plan=plan,
        inputs={"request": 123},
        runs_dir=str(runs_dir),
        run_id=run_id,
        resume_run_id="",
        ai_socket="unused-by-stub",
        workspace=str(root),
        work_dir=str(root),
        complete_step=complete,
    )
    second = await run_flow_tool._execute_graph(
        source=_AGENT_WORKFLOW,
        compiled=compiled,
        plan=plan,
        inputs={"request": "123"},
        runs_dir=str(runs_dir),
        run_id=run_id,
        resume_run_id=run_id,
        ai_socket="unused-by-stub",
        workspace=str(root),
        work_dir=str(root),
        complete_step=complete,
    )

    assert calls == [123, "123"]
    assert first == {"result": "int:123"}
    assert second == {"result": "str:123"}
    assert await (runs_dir / run_id / "input" / "request.md").read_text(encoding="utf-8") == '"123"'


@pytest.mark.anyio
async def test_resume_cache_tracks_instruction_workspace_and_model_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    root = anyio.Path(str(tmp_path))
    runs_dir = root / "runs"
    run_id = "instruction-cache"
    instruction = root / "instruction.md"
    source = _AGENT_WORKFLOW.replace(
        "step_instruction(review_step) == review_instruction;",
        'step_instruction(review_step) == "instruction.md";',
    )
    compiled, plan = run_flow_tool._preflight(source, {"request": "review this"})
    calls: list[str] = []
    monkeypatch.setenv("PSI_AI_MODEL", "model-a")

    async def complete(
        step: Any,
        output_ids: tuple[str, ...],
        inputs: Mapping[str, object],
    ) -> str:
        del step, output_ids, inputs
        content = await instruction.read_text(encoding="utf-8")
        calls.append(content)
        return content

    async def execute(*, resume: bool) -> dict[str, object]:
        return await run_flow_tool._execute_graph(
            source=source,
            compiled=compiled,
            plan=plan,
            inputs={"request": "review this"},
            runs_dir=str(runs_dir),
            run_id=run_id,
            resume_run_id=run_id if resume else "",
            ai_socket="unused-by-stub",
            workspace=str(root),
            work_dir=str(root),
            complete_step=complete,
        )

    await instruction.write_text("old", encoding="utf-8")
    first = await execute(resume=False)
    unchanged = await execute(resume=True)
    await instruction.write_text("new", encoding="utf-8")
    changed = await execute(resume=True)
    tools_dir = root / "tools"
    await tools_dir.mkdir()
    await (tools_dir / "cache_tool.py").write_text(
        'async def cache_tool() -> str:\n    return "changed"\n',
        encoding="utf-8",
    )
    workspace_changed = await execute(resume=True)
    await (root / "AGENTS.md").write_text("changed prompt", encoding="utf-8")
    prompt_changed = await execute(resume=True)
    monkeypatch.setenv("PSI_AI_MODEL", "model-b")
    model_changed = await execute(resume=True)

    assert calls == ["old", "new", "new", "new", "new"]
    assert first == unchanged == {"result": "old"}
    assert changed == {"result": "new"}
    assert workspace_changed == {"result": "new"}
    assert prompt_changed == {"result": "new"}
    assert model_changed == {"result": "new"}


@pytest.mark.anyio
async def test_instruction_file_must_not_escape_the_working_directory(tmp_path: Any) -> None:
    root = anyio.Path(str(tmp_path))
    work_dir = root / "work"
    outside = root / "outside.md"
    instruction = work_dir / "instruction.md"
    await work_dir.mkdir()
    await outside.write_text("outside", encoding="utf-8")
    try:
        await instruction.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"symbolic links are unavailable: {error}")

    with pytest.raises(ValueError, match="escapes"):
        await run_flow_tool._prepare_instruction(
            "instruction.md",
            work_dir=str(work_dir),
        )


@pytest.mark.anyio
async def test_status_and_result_read_completed_execution_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    compiled, plan = run_flow_tool._preflight(_AGENT_WORKFLOW, {"request": "review this"})
    root = anyio.Path(str(tmp_path))

    async def complete(
        step: Any,
        output_ids: tuple[str, ...],
        inputs: Mapping[str, object],
    ) -> str:
        del step, output_ids, inputs
        return "done"

    run_id = "completed-run"
    runs_dir = root / "runs"
    run_dir = runs_dir / run_id
    state_dir = root / "state"
    monkeypatch.setenv("FLOW_NEXT_RUN_STATE_DIR", str(state_dir))
    token = run_flow_tool._make_run_token()
    attempt_id = run_flow_tool._make_attempt_id()
    await run_flow_tool._execute_graph(
        source=_AGENT_WORKFLOW,
        compiled=compiled,
        plan=plan,
        inputs={"request": "review this"},
        runs_dir=str(runs_dir),
        run_id=run_id,
        resume_run_id="",
        ai_socket="unused-by-stub",
        workspace=str(root),
        work_dir=str(root),
        complete_step=complete,
    )

    state = {
        "run_token": token,
        "attempt_id": attempt_id,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "pid": 0,
        "cursor": 0,
        "progress_offset": 0,
        "started_ts": 1.0,
        "log_path": str(state_dir / "worker.log"),
    }
    await run_flow_tool._atomic_write_json(
        run_flow_tool._state_path(token),
        state,
    )
    await run_flow_tool._seal_attempt_terminal(token, state)

    status = json.loads(await run_flow_tool.run_flow("status", run_token=token, window_seconds=0.01))
    result = json.loads(await run_flow_tool.run_flow("result", run_token=token))

    assert status["ok"] is True
    assert status["done"] is True
    assert status["status"] == "ok"
    assert status["completed"] == 2
    assert result["ok"] is True
    assert result["status"] == "ok"
    assert result["outputs"] == {"result": "done"}
    assert result["bindings"]["result"] == "done"
    assert result["workflow_graph"]["workflow_id"] == "review"
    assert result["execution_graph"]["run_id"] == run_id


@pytest.mark.anyio
async def test_resume_keeps_each_token_bound_to_its_attempt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    compiled, plan = run_flow_tool._preflight(_AGENT_WORKFLOW, {"request": "review this"})
    root = anyio.Path(str(tmp_path))
    runs_dir = root / "runs"
    run_id = "resumed-run"
    run_dir = runs_dir / run_id
    state_dir = root / "state"
    monkeypatch.setenv("FLOW_NEXT_RUN_STATE_DIR", str(state_dir))
    first_token = run_flow_tool._make_run_token()
    first_attempt = run_flow_tool._make_attempt_id()

    async def first_completion(
        step: Any,
        output_ids: tuple[str, ...],
        inputs: Mapping[str, object],
    ) -> str:
        del step, output_ids, inputs
        return "cached result"

    await run_flow_tool._execute_graph(
        source=_AGENT_WORKFLOW,
        compiled=compiled,
        plan=plan,
        inputs={"request": "review this"},
        runs_dir=str(runs_dir),
        run_id=run_id,
        resume_run_id="",
        ai_socket="unused-by-stub",
        workspace=str(root),
        work_dir=str(root),
        complete_step=first_completion,
    )
    first_state = {
        "run_token": first_token,
        "attempt_id": first_attempt,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "pid": 0,
        "cursor": 0,
        "progress_offset": 0,
        "started_ts": 1.0,
        "log_path": str(state_dir / "first.log"),
    }
    await run_flow_tool._atomic_write_json(
        run_flow_tool._state_path(first_token),
        first_state,
    )
    await run_flow_tool._seal_attempt_terminal(first_token, first_state)

    progress_offset = len(await run_flow_tool._read_progress(str(run_dir)))
    second_token = run_flow_tool._make_run_token()
    second_attempt = run_flow_tool._make_attempt_id()
    second_state = {
        "run_token": second_token,
        "attempt_id": second_attempt,
        "run_id": run_id,
        "resume_run_id": run_id,
        "run_dir": str(run_dir),
        "pid": 0,
        "cursor": 0,
        "progress_offset": progress_offset,
        "started_ts": 2.0,
        "log_path": str(state_dir / "second.log"),
    }
    await run_flow_tool._atomic_write_json(
        run_flow_tool._state_path(second_token),
        second_state,
    )
    stale_result = json.loads(await run_flow_tool.run_flow("result", run_token=second_token))
    first_during_resume = json.loads(await run_flow_tool.run_flow("result", run_token=first_token))
    first_status_during_resume = json.loads(
        await run_flow_tool.run_flow("status", run_token=first_token, window_seconds=0.01)
    )
    assert stale_result == {
        "ok": False,
        "message": "current run has not finished yet",
        "done": False,
    }
    assert first_during_resume["outputs"] == {"result": "cached result"}
    assert first_status_during_resume["done"] is True

    async def second_completion(
        step: Any,
        output_ids: tuple[str, ...],
        inputs: Mapping[str, object],
    ) -> str:
        del step, output_ids, inputs
        return "new result"

    await (run_dir / "meta.json").unlink()
    outputs = await run_flow_tool._execute_graph(
        source=_AGENT_WORKFLOW,
        compiled=compiled,
        plan=plan,
        inputs={"request": "changed request"},
        runs_dir=str(runs_dir),
        run_id=run_id,
        resume_run_id=run_id,
        ai_socket="unused-by-stub",
        workspace=str(root),
        work_dir=str(root),
        complete_step=second_completion,
    )
    await run_flow_tool._seal_attempt_terminal(second_token, second_state)
    first_result = json.loads(await run_flow_tool.run_flow("result", run_token=first_token))
    second_result = json.loads(await run_flow_tool.run_flow("result", run_token=second_token))

    assert outputs == {"result": "new result"}
    assert first_result["outputs"] == {"result": "cached result"}
    assert second_result["outputs"] == {"result": "new result"}
    assert first_result["attempt_id"] == first_attempt
    assert second_result["attempt_id"] == second_attempt
    assert first_result["meta"][run_flow_tool._META_ATTEMPT_ID] == first_attempt
    assert second_result["meta"][run_flow_tool._META_ATTEMPT_ID] == second_attempt
    assert first_result["meta"][run_flow_tool._META_TOKEN_DIGEST] == run_flow_tool._run_token_digest(first_token)
    assert second_result["meta"][run_flow_tool._META_TOKEN_DIGEST] == run_flow_tool._run_token_digest(second_token)
    assert first_result["bindings"]["result"] == "cached result"
    assert second_result["bindings"]["result"] == "new result"
    assert "cached result" in json.dumps(first_result["execution_graph"])
    assert "new result" not in json.dumps(first_result["execution_graph"])
    assert "new result" in json.dumps(second_result["execution_graph"])


@pytest.mark.anyio
async def test_failed_resume_never_returns_outputs_from_the_previous_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    root = anyio.Path(str(tmp_path))
    runs_dir = root / "runs"
    run_id = "failed-resume"
    compiled, plan = run_flow_tool._preflight(_AGENT_WORKFLOW, {"request": "review this"})

    async def first_completion(
        step: Any,
        output_ids: tuple[str, ...],
        inputs: Mapping[str, object],
    ) -> str:
        del step, output_ids, inputs
        return "old success"

    await run_flow_tool._execute_graph(
        source=_AGENT_WORKFLOW,
        compiled=compiled,
        plan=plan,
        inputs={"request": "review this"},
        runs_dir=str(runs_dir),
        run_id=run_id,
        resume_run_id="",
        ai_socket="unused-by-stub",
        workspace=str(root),
        work_dir=str(root),
        complete_step=first_completion,
    )

    run_dir = runs_dir / run_id
    state_dir = root / "state"
    monkeypatch.setenv("FLOW_NEXT_RUN_STATE_DIR", str(state_dir))
    token = run_flow_tool._make_run_token()
    attempt_id = run_flow_tool._make_attempt_id()
    state = {
        "run_token": token,
        "attempt_id": attempt_id,
        "run_id": run_id,
        "resume_run_id": run_id,
        "run_dir": str(run_dir),
        "pid": 0,
        "cursor": 0,
        "progress_offset": len(await run_flow_tool._read_progress(str(run_dir))),
        "started_ts": 1.0,
        "log_path": str(state_dir / "worker.log"),
    }
    await run_flow_tool._atomic_write_json(
        run_flow_tool._state_path(token),
        state,
    )
    await (run_dir / "meta.json").unlink()

    changed_source = _AGENT_WORKFLOW.replace("review_instruction", "changed_instruction")
    changed_compiled, changed_plan = run_flow_tool._preflight(changed_source, {"request": "review this"})

    async def failed_completion(
        step: Any,
        output_ids: tuple[str, ...],
        inputs: Mapping[str, object],
    ) -> str:
        del step, output_ids, inputs
        raise RuntimeError("current execution failed")

    with pytest.raises(RuntimeError, match="current execution failed"):
        await run_flow_tool._execute_graph(
            source=changed_source,
            compiled=changed_compiled,
            plan=changed_plan,
            inputs={"request": "review this"},
            runs_dir=str(runs_dir),
            run_id=run_id,
            resume_run_id=run_id,
            ai_socket="unused-by-stub",
            workspace=str(root),
            work_dir=str(root),
            complete_step=failed_completion,
        )

    await run_flow_tool._seal_attempt_terminal(token, state)
    meta = await run_flow_tool._read_json_object(run_dir / "meta.json")
    assert meta is not None
    assert "current execution failed" in str(meta["error"])
    result = json.loads(await run_flow_tool.run_flow("result", run_token=token))
    assert result["ok"] is True
    assert result["status"] == "error"
    assert result["outputs"] is None


@pytest.mark.anyio
async def test_resume_start_rejects_an_overlapping_worker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    root = anyio.Path(str(tmp_path))
    runs_dir = root / "runs"
    run_id = "locked-resume"
    compiled, plan = run_flow_tool._preflight(_AGENT_WORKFLOW, {"request": "review this"})

    async def complete(
        step: Any,
        output_ids: tuple[str, ...],
        inputs: Mapping[str, object],
    ) -> str:
        del step, output_ids, inputs
        return "ready to resume"

    await run_flow_tool._execute_graph(
        source=_AGENT_WORKFLOW,
        compiled=compiled,
        plan=plan,
        inputs={"request": "review this"},
        runs_dir=str(runs_dir),
        run_id=run_id,
        resume_run_id="",
        ai_socket="unused-by-stub",
        workspace=str(root),
        work_dir=str(root),
        complete_step=complete,
    )
    source_path = root / "review.g4"
    await source_path.write_text(_AGENT_WORKFLOW, encoding="utf-8")
    monkeypatch.setenv("FLOW_NEXT_RUN_STATE_DIR", str(root / "state"))
    monkeypatch.setattr(run_flow_tool, "_resolve_ai_socket", lambda: "http://127.0.0.1:9999")

    async def spawn_worker(state_path: anyio.Path, *, cwd: str) -> int:
        del state_path, cwd
        return 4242

    monkeypatch.setattr(run_flow_tool, "_spawn_worker", spawn_worker)

    first = json.loads(
        await run_flow_tool.run_flow(
            "start",
            flow_path=str(source_path),
            inputs_json='{"request":"review this"}',
            cwd=str(root),
            resume_run_id=run_id,
        )
    )
    second = json.loads(
        await run_flow_tool.run_flow(
            "start",
            flow_path=str(source_path),
            inputs_json='{"request":"review this"}',
            cwd=str(root),
            resume_run_id=run_id,
        )
    )
    first_state = await run_flow_tool._read_json_object(run_flow_tool._state_path(first["run_token"]))

    assert first["ok"] is True
    assert second["ok"] is False
    assert "already locked" in second["message"]
    assert first_state is not None
    lock_dir = anyio.Path(str(first_state["lock_dir"]))
    assert await run_flow_tool._release_run_lock(lock_dir, expected_token=first["run_token"])


@pytest.mark.anyio
async def test_resume_rejects_a_symlinked_run_directory(tmp_path: Any) -> None:
    root = anyio.Path(str(tmp_path))
    runs_dir = root / "runs"
    outside = root / "outside"
    await runs_dir.mkdir()
    await outside.mkdir()
    link = runs_dir / "linked-run"
    try:
        await link.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symbolic links are unavailable: {error}")

    with pytest.raises(ValueError, match="symbolic link"):
        await run_flow_tool._resolve_run_dir(
            str(runs_dir),
            "linked-run",
            resume=True,
        )


@pytest.mark.anyio
async def test_resume_rejects_a_legacy_run_without_g4_provenance(
    tmp_path: Any,
) -> None:
    root = anyio.Path(str(tmp_path))
    source_path = root / "review.g4"
    await source_path.write_text(_AGENT_WORKFLOW, encoding="utf-8")
    legacy_run = root / "runs" / "legacy-run"
    for directory in ("input", "bindings", "trace"):
        await (legacy_run / directory).mkdir(parents=True, exist_ok=True)
    await (legacy_run / "meta.json").write_text(
        '{"status":"ok"}',
        encoding="utf-8",
    )

    result = json.loads(
        await run_flow_tool.run_flow(
            "start",
            flow_path=str(source_path),
            inputs_json='{"request":"review this"}',
            cwd=str(root),
            resume_run_id="legacy-run",
        )
    )

    assert result["ok"] is False
    assert result["error_type"] == "ValueError"
    assert "was not created by FusionFlow Next run_flow" in result["message"]
    assert not await (legacy_run / "workflow.g4").exists()


@pytest.mark.anyio
async def test_resume_rejects_a_different_g4_workflow_identity(
    tmp_path: Any,
) -> None:
    root = anyio.Path(str(tmp_path))
    run_id = "review-run"
    compiled, plan = run_flow_tool._preflight(
        _AGENT_WORKFLOW,
        {"request": "review this"},
    )

    async def complete(
        step: Any,
        output_ids: tuple[str, ...],
        inputs: Mapping[str, object],
    ) -> str:
        del step, output_ids, inputs
        return "reviewed"

    await run_flow_tool._execute_graph(
        source=_AGENT_WORKFLOW,
        compiled=compiled,
        plan=plan,
        inputs={"request": "review this"},
        runs_dir=str(root / "runs"),
        run_id=run_id,
        resume_run_id="",
        ai_socket="unused-by-stub",
        workspace=str(root),
        work_dir=str(root),
        complete_step=complete,
    )
    source_path = root / "merge.g4"
    await source_path.write_text(_TWO_INPUT_WORKFLOW, encoding="utf-8")

    result = json.loads(
        await run_flow_tool.run_flow(
            "start",
            flow_path=str(source_path),
            inputs_json='{"left":"a","right":"b"}',
            cwd=str(root),
            resume_run_id=run_id,
        )
    )

    assert result["ok"] is False
    assert result["error_type"] == "ValueError"
    assert "invalid FusionFlow Next run_flow provenance" in result["message"]
    assert await (root / "runs" / run_id / "workflow.g4").read_text(encoding="utf-8") == _AGENT_WORKFLOW
