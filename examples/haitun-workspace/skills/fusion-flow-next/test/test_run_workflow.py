from __future__ import annotations

import importlib.util
import json
import os
import sys
from typing import Any, cast

import pytest
from fusion_flow_next.execution import AgentConfig, AgentInvocation, ExecResult

_SKILL_DIR = os.path.dirname(os.path.dirname(__file__))
_RUNNER_PATH = os.path.join(_SKILL_DIR, "examples", "run_workflow.py")


def _load_module(name: str, path: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return cast(Any, module)


run_workflow = _load_module("fusion_flow_next_workflow_runner", _RUNNER_PATH)


def _dispatch_workflow(
    executor_kind: str | None,
    instruction: str,
    *,
    executor_configuration: str = "",
) -> str:
    executor_declaration = "" if executor_kind is None else f"const worker: {executor_kind};"
    return f"""
const dispatch: Workflow;
const dispatch_step: Step;
const dispatch_name: StepName;
{executor_declaration}
const request: Artifact;
const result: Artifact;

workflow dispatch {{
    input_workflow(dispatch, request) == True;
    output_workflow(dispatch, result) == True;
    {executor_configuration}
    step_name(dispatch_step) == dispatch_name;
    step_instruction(dispatch_step) == "{instruction}";
    step_executor(dispatch_step) == worker;
    consumes(dispatch_step, request) == True;
    produces(dispatch_step, result) == True;
}}
"""


@pytest.mark.parametrize(
    ("executor_kind", "configuration", "field", "expected"),
    [
        ("Program", 'program_path(worker) == "./bin/worker";', "program_paths", {"worker": "./bin/worker"}),
        (
            "Agent",
            '"./instructions/worker.md" == agent_system(worker);',
            "agent_systems",
            {"worker": "./instructions/worker.md"},
        ),
    ],
)
def test_compile_workflow_extracts_executor_configuration(
    executor_kind: str,
    configuration: str,
    field: str,
    expected: dict[str, str],
) -> None:
    compiled = run_workflow.compile_workflow(
        _dispatch_workflow(
            executor_kind,
            "do_work",
            executor_configuration=configuration,
        )
    )

    assert getattr(compiled, field) == expected


def test_compile_workflow_requires_program_path() -> None:
    with pytest.raises(ValueError, match="has no program_path"):
        run_workflow.compile_workflow(_dispatch_workflow("Program", "do_work"))


def test_compile_workflow_rejects_duplicate_executor_configuration() -> None:
    with pytest.raises(ValueError, match="duplicate program_path"):
        run_workflow.compile_workflow(
            _dispatch_workflow(
                "Program",
                "do_work",
                executor_configuration="""
                program_path(worker) == "./bin/first";
                program_path(worker) == "./bin/second";
                """,
            )
        )


def test_compile_workflow_rejects_unknown_residual_assertion() -> None:
    with pytest.raises(ValueError, match="graph compiler cannot execute"):
        run_workflow.compile_workflow(
            _dispatch_workflow(
                "Agent",
                "do_work",
                executor_configuration="worker == worker;",
            )
        )


@pytest.mark.anyio
async def test_agent_executes_with_step_instruction_and_artifact_context(tmp_path: Any) -> None:
    calls: list[tuple[AgentConfig, AgentInvocation]] = []

    async def runner(config: AgentConfig, invocation: AgentInvocation) -> str:
        calls.append((config, invocation))
        return "completed"

    result = await run_workflow.execute_workflow(
        _dispatch_workflow("Agent", "summarize_request"),
        inputs={"request": "Explain structured concurrency."},
        runner=runner,
        runs_dir=tmp_path / "runs",
    )

    assert result == {"result": "completed"}
    assert calls[0][0].system
    assert calls[0][1].prompt == "summarize_request"
    assert calls[0][1].context == {"request": "Explain structured concurrency."}


@pytest.mark.anyio
async def test_agent_system_is_resolved_into_agent_config(tmp_path: Any) -> None:
    references: list[str] = []
    calls: list[tuple[AgentConfig, AgentInvocation]] = []

    async def resolve_instruction(reference: str) -> str:
        references.append(reference)
        return "You are a precise workflow analyst."

    async def runner(config: AgentConfig, invocation: AgentInvocation) -> str:
        calls.append((config, invocation))
        return "completed"

    result = await run_workflow.execute_workflow(
        _dispatch_workflow(
            "Agent",
            "./instructions/missing-agent.txt",
            executor_configuration='agent_system(worker) == "./instructions/worker-system.md";',
        ),
        inputs={"request": "Do the work."},
        runner=runner,
        resolve_instruction=resolve_instruction,
        runs_dir=tmp_path / "runs",
    )

    assert result == {"result": "completed"}
    assert references == ["./instructions/worker-system.md"]
    assert calls[0][0].system == "You are a precise workflow analyst."
    assert calls[0][1].prompt == "./instructions/missing-agent.txt"


@pytest.mark.anyio
async def test_agent_system_requires_instruction_resolver(tmp_path: Any) -> None:
    async def runner(config: AgentConfig, invocation: AgentInvocation) -> str:
        pytest.fail(f"runner called with {config!r}, {invocation!r}")

    with pytest.raises(ValueError, match="has agent_system but no instruction resolver"):
        await run_workflow.execute_workflow(
            _dispatch_workflow(
                "Agent",
                "do_work",
                executor_configuration='agent_system(worker) == "./instructions/worker-system.md";',
            ),
            inputs={"request": "Do the work."},
            runner=runner,
            runs_dir=tmp_path / "runs",
        )


@pytest.mark.anyio
async def test_program_path_is_executed_with_instruction_and_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    calls: list[dict[str, object]] = []
    path_references: list[str] = []

    async def resolve_path(reference: str) -> str:
        path_references.append(reference)
        return "./bin/worker"

    async def execute_program(
        name: str,
        argv: tuple[str, ...],
        *,
        stdin: str,
        cwd: Any,
        binding_name: str,
    ) -> ExecResult:
        calls.append(
            {
                "name": name,
                "argv": argv,
                "stdin": stdin,
                "cwd": cwd,
                "binding_name": binding_name,
            }
        )
        return ExecResult(stdout="completed", raw="completed", exit_code=0, duration_ms=1)

    monkeypatch.setattr(run_workflow.flow, "exec", execute_program)
    result = await run_workflow.execute_workflow(
        _dispatch_workflow(
            "Program",
            "./instructions/missing-program.txt",
            executor_configuration="program_path(worker) == worker_path;",
        ),
        inputs={"request": {"topic": "structured concurrency"}},
        resolve_path=resolve_path,
        runs_dir=tmp_path / "runs",
        work_dir=tmp_path,
    )

    assert result == {"result": "completed"}
    assert path_references == ["worker_path"]
    assert calls[0]["name"] == "worker"
    assert calls[0]["argv"] == ("./bin/worker",)
    assert calls[0]["cwd"] == tmp_path
    assert calls[0]["binding_name"] == "dispatch_step"
    stdin = calls[0]["stdin"]
    assert isinstance(stdin, str)
    assert json.loads(stdin) == {
        "instruction": "./instructions/missing-program.txt",
        "inputs": {"request": {"topic": "structured concurrency"}},
    }


@pytest.mark.anyio
async def test_relative_program_path_requires_work_dir(tmp_path: Any) -> None:
    with pytest.raises(ValueError, match="relative program_path requires an explicit work_dir"):
        await run_workflow.execute_workflow(
            _dispatch_workflow(
                "Program",
                "do_work",
                executor_configuration='program_path(worker) == "./bin/worker";',
            ),
            inputs={"request": "Do the work."},
            runs_dir=tmp_path / "runs",
        )


@pytest.mark.anyio
async def test_untyped_executor_defaults_to_agent(tmp_path: Any) -> None:
    prompts: list[str] = []

    async def runner(config: AgentConfig, invocation: AgentInvocation) -> str:
        del config
        prompts.append(invocation.prompt)
        return "completed"

    instruction = "./instructions/untyped-agent.txt"
    result = await run_workflow.execute_workflow(
        _dispatch_workflow(None, instruction),
        inputs={"request": "Do the work."},
        runner=runner,
        runs_dir=tmp_path / "runs",
    )

    assert result == {"result": "completed"}
    assert prompts == [instruction]


@pytest.mark.anyio
async def test_human_instruction_is_prepared_by_agent_before_request(tmp_path: Any) -> None:
    preparation_prompts: list[str] = []
    human_prompts: list[str] = []

    async def prepare_human_instruction(prompt: str) -> str:
        preparation_prompts.append(prompt)
        return "Review the supplied proposal and answer approve or reject."

    async def request_human(prompt: str) -> object:
        human_prompts.append(prompt)
        return {"decision": "approve"}

    result = await run_workflow.execute_workflow(
        _dispatch_workflow("Human", "./instructions/../proposal.txt"),
        inputs={"request": "proposal-v2"},
        prepare_human_instruction=prepare_human_instruction,
        request_human=request_human,
        runs_dir=tmp_path / "runs",
    )

    assert result == {"result": {"decision": "approve"}}
    assert len(preparation_prompts) == 1
    assert "Step: dispatch_step" in preparation_prompts[0]
    assert "Instruction or reference: ./instructions/../proposal.txt" in preparation_prompts[0]
    assert '"request": "proposal-v2"' in preparation_prompts[0]
    assert "available tools and normal approval flow" in preparation_prompts[0]
    assert human_prompts == ["Review the supplied proposal and answer approve or reject."]


@pytest.mark.anyio
async def test_human_preparation_failure_does_not_request_human(tmp_path: Any) -> None:
    async def prepare_human_instruction(prompt: str) -> str:
        del prompt
        raise PermissionError("resource access was not approved")

    async def request_human(prompt: str) -> str:
        pytest.fail(f"human called with {prompt!r}")

    with pytest.RaisesGroup(pytest.RaisesExc(PermissionError, match="not approved")):
        await run_workflow.execute_workflow(
            _dispatch_workflow("Human", "./private/reference.txt"),
            inputs={"request": "review"},
            prepare_human_instruction=prepare_human_instruction,
            request_human=request_human,
            runs_dir=tmp_path / "runs",
        )


@pytest.mark.anyio
async def test_human_preparation_must_return_text(tmp_path: Any) -> None:
    async def prepare_human_instruction(prompt: str) -> str:
        del prompt
        return "  "

    async def request_human(prompt: str) -> str:
        pytest.fail(f"human called with {prompt!r}")

    with pytest.RaisesGroup(pytest.RaisesExc(ValueError, match="preparation returned no text")):
        await run_workflow.execute_workflow(
            _dispatch_workflow("Human", "review_reference"),
            inputs={"request": "review"},
            prepare_human_instruction=prepare_human_instruction,
            request_human=request_human,
            runs_dir=tmp_path / "runs",
        )


@pytest.mark.anyio
async def test_human_step_requires_preparer_and_requester(tmp_path: Any) -> None:
    with pytest.RaisesGroup(pytest.RaisesExc(ValueError, match="requires prepare_human_instruction and request_human")):
        await run_workflow.execute_workflow(
            _dispatch_workflow("Human", "review_reference"),
            inputs={"request": "review"},
            runs_dir=tmp_path / "runs",
        )
