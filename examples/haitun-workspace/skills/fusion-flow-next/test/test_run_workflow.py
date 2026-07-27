from __future__ import annotations

import importlib.util
import os
import sys
from typing import Any, cast

import anyio
import pytest

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


def _dispatch_workflow(executor_kind: str, instruction: str) -> str:
    return f"""
const dispatch: Workflow;
const dispatch_step: Step;
const dispatch_name: StepName;
const worker: {executor_kind};
const request: Artifact;
const result: Artifact;

workflow dispatch {{
    input_workflow(dispatch, request) == True;
    output_workflow(dispatch, result) == True;
    step_name(dispatch_step) == dispatch_name;
    step_instruction(dispatch_step) == "{instruction}";
    step_executor(dispatch_step) == worker;
    consumes(dispatch_step, request) == True;
    produces(dispatch_step, result) == True;
}}
"""


@pytest.mark.anyio
async def test_in_memory_workflow_compiles_and_executes() -> None:
    prompts: list[str] = []

    async def complete(prompt: str) -> str:
        prompts.append(prompt)
        return "completed"

    result = await run_workflow.execute_workflow(
        _dispatch_workflow("Agent", "summarize_request"),
        workflow_path="memory.workflow",
        request="Explain structured concurrency.",
        complete=complete,
    )

    assert result == {"result": "completed"}
    assert prompts[0].splitlines()[0] == "Instruction: summarize_request"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("executor_kind", "instruction"),
    [
        ("Agent", "./instructions/missing-agent.txt"),
        ("Program", "./instructions/missing-program.txt"),
    ],
)
async def test_non_human_executor_receives_instruction_path_unchanged(
    executor_kind: str,
    instruction: str,
) -> None:
    prompts: list[str] = []

    async def complete(prompt: str) -> str:
        prompts.append(prompt)
        return "completed"

    result = await run_workflow.execute_workflow(
        _dispatch_workflow(executor_kind, instruction),
        workflow_path="dispatch.workflow",
        request="Do the work.",
        complete=complete,
    )

    assert result == {"result": "completed"}
    assert prompts[0].splitlines()[0] == f"Instruction: {instruction}"
    assert f'"{instruction}"' not in prompts[0]


@pytest.mark.anyio
async def test_human_executor_receives_utf8_instruction_contents(tmp_path: object) -> None:
    instructions_dir = os.path.join(str(tmp_path), "instructions")
    await anyio.Path(instructions_dir).mkdir()
    instruction_path = "./instructions/human.txt"
    expected = "请人工核对输入,并只返回确认结果。"
    await anyio.Path(os.path.join(instructions_dir, "human.txt")).write_text(expected, encoding="utf-8")
    prompts: list[str] = []

    async def complete(prompt: str) -> str:
        prompts.append(prompt)
        return "confirmed"

    result = await run_workflow.execute_workflow(
        _dispatch_workflow("Human", instruction_path),
        workflow_path=os.path.join(str(tmp_path), "human.workflow"),
        request="请核对。",
        complete=complete,
    )

    assert result == {"result": "confirmed"}
    assert f"Instruction: {expected}" in prompts[0]
    assert instruction_path not in prompts[0]


@pytest.mark.anyio
async def test_human_instruction_dispatch_error_identifies_step_and_path(tmp_path: object) -> None:
    instruction_path = "./missing.txt"
    compiled = run_workflow.compile_workflow(_dispatch_workflow("Human", instruction_path))

    async def complete(prompt: str) -> str:
        pytest.fail(f"completion called with {prompt!r}")

    dispatch = run_workflow._build_dispatch(
        compiled,
        complete,
        os.path.join(str(tmp_path), "missing.workflow"),
    )
    (step,) = compiled.graph.steps

    with pytest.raises(ValueError) as error:
        await dispatch(step, {"request": "Do the work."})

    assert step.step_id in str(error.value)
    assert instruction_path in str(error.value)


@pytest.mark.anyio
async def test_human_instruction_dispatch_hides_physical_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instruction_path = "./private.txt"
    physical_path = "/credentials/private.txt"

    async def deny_read(workflow_path: str, logical_path: str) -> str:
        del workflow_path, logical_path
        raise PermissionError(physical_path)

    async def complete(prompt: str) -> str:
        pytest.fail(f"completion called with {prompt!r}")

    monkeypatch.setattr(run_workflow, "_read_human_instruction", deny_read)
    compiled = run_workflow.compile_workflow(_dispatch_workflow("Human", instruction_path))
    dispatch = run_workflow._build_dispatch(compiled, complete, "private.workflow")
    (step,) = compiled.graph.steps

    with pytest.raises(ValueError) as error:
        await dispatch(step, {"request": "Do the work."})

    assert step.step_id in str(error.value)
    assert instruction_path in str(error.value)
    assert physical_path not in str(error.value)


@pytest.mark.anyio
async def test_human_instruction_rejects_empty_file(tmp_path: object) -> None:
    instruction_path = os.path.join(str(tmp_path), "empty.txt")
    await anyio.Path(instruction_path).write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="must not be empty"):
        await run_workflow._read_human_instruction(
            os.path.join(str(tmp_path), "empty.workflow"),
            "./empty.txt",
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "instruction_path",
    [
        "/absolute/instruction.txt",
        "C:/instruction.txt",
        r"\\server\share\instruction.txt",
    ],
)
async def test_human_instruction_rejects_absolute_drive_and_unc_paths(
    tmp_path: object,
    instruction_path: str,
) -> None:
    with pytest.raises(ValueError, match="relative"):
        await run_workflow._read_human_instruction(
            os.path.join(str(tmp_path), "absolute.workflow"),
            instruction_path,
        )


@pytest.mark.anyio
async def test_human_instruction_rejects_parent_segments(tmp_path: object) -> None:
    with pytest.raises(ValueError, match=r"\.\."):
        await run_workflow._read_human_instruction(
            os.path.join(str(tmp_path), "parent.workflow"),
            "./instructions/../secret.txt",
        )


@pytest.mark.anyio
async def test_human_instruction_rejects_directory(tmp_path: object) -> None:
    instruction_path = os.path.join(str(tmp_path), "directory")
    await anyio.Path(instruction_path).mkdir()

    with pytest.raises(ValueError, match="regular file"):
        await run_workflow._read_human_instruction(
            os.path.join(str(tmp_path), "directory.workflow"),
            "./directory",
        )


@pytest.mark.anyio
async def test_human_instruction_rejects_invalid_utf8(tmp_path: object) -> None:
    instruction_path = os.path.join(str(tmp_path), "invalid.txt")
    await anyio.Path(instruction_path).write_bytes(b"\xff")

    with pytest.raises(ValueError, match="UTF-8"):
        await run_workflow._read_human_instruction(
            os.path.join(str(tmp_path), "invalid.workflow"),
            "./invalid.txt",
        )


@pytest.mark.anyio
async def test_human_instruction_rejects_symlink_escape(tmp_path: object) -> None:
    workflow_dir = os.path.join(str(tmp_path), "workflow")
    await anyio.Path(workflow_dir).mkdir()
    outside_path = os.path.join(str(tmp_path), "outside.txt")
    await anyio.Path(outside_path).write_text("outside", encoding="utf-8")
    link_path = os.path.join(workflow_dir, "link.txt")
    try:
        await anyio.Path(link_path).symlink_to(outside_path)
    except OSError as error:
        pytest.skip(f"symlink creation denied: {error}")

    with pytest.raises(ValueError, match="escapes"):
        await run_workflow._read_human_instruction(
            os.path.join(workflow_dir, "escape.workflow"),
            "./link.txt",
        )


@pytest.mark.anyio
async def test_human_instruction_requires_workflow_path(tmp_path: object) -> None:
    with pytest.raises(ValueError, match=r"\.workflow"):
        await run_workflow._read_human_instruction(
            os.path.join(str(tmp_path), "workflow.txt"),
            "./missing.txt",
        )
