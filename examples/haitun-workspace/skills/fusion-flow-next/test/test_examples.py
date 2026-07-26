from __future__ import annotations

import importlib.util
import os
import sys
from typing import Any, cast

import anyio
import pytest

from psi_agent.workflow_execution import Await, generate_plan

_SKILL_DIR = os.path.dirname(os.path.dirname(__file__))
_EXAMPLES_DIR = os.path.join(_SKILL_DIR, "examples")
_FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
_CATALYST_WORKFLOW = os.path.join(_EXAMPLES_DIR, "catalyst", "catalyst.workflow")


def _load_module(name: str, path: str, package_paths: list[str] | None = None) -> Any:
    spec = importlib.util.spec_from_file_location(name, path, submodule_search_locations=package_paths)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return cast(Any, module)


_PACKAGE_DIR = os.path.join(_SKILL_DIR, "fusion_flow_next")
_load_module(
    "fusion_flow_next",
    os.path.join(_PACKAGE_DIR, "__init__.py"),
    [_PACKAGE_DIR],
)
run_workflow = _load_module(
    "fusion_flow_next_example_runner",
    os.path.join(_EXAMPLES_DIR, "run_workflow.py"),
)


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
@pytest.mark.parametrize(
    ("filename", "step_count", "largest_await"),
    [
        ("single_step.workflow", 1, 0),
        ("sequential.workflow", 2, 1),
        ("parallel_join.workflow", 3, 2),
    ],
)
async def test_examples_parse_compile_plan_and_execute(
    filename: str,
    step_count: int,
    largest_await: int,
) -> None:
    source = await anyio.Path(os.path.join(_EXAMPLES_DIR, filename)).read_text()
    compiled = run_workflow.compile_workflow(source)
    graph = compiled.graph
    plan = generate_plan(graph)
    prompts: list[str] = []

    async def complete(prompt: str) -> str:
        prompts.append(prompt)
        return "ok"

    result = await run_workflow.execute_workflow(
        source,
        workflow_path=os.path.join(_EXAMPLES_DIR, filename),
        request="Explain structured concurrency.",
        complete=complete,
    )
    await_sizes = [
        len(instruction.step_ids)
        for fiber in plan.fibers
        for instruction in fiber.instructions
        if isinstance(instruction, Await)
    ]

    assert len(graph.steps) == step_count
    assert all(step.instruction_id is not None for step in graph.steps)
    assert max(await_sizes, default=0) == largest_await
    assert result == {"result": "ok"}
    assert len(prompts) == step_count
    assert all(any(f"Instruction: {step.instruction_id}" in prompt for prompt in prompts) for step in graph.steps)


@pytest.mark.anyio
async def test_catalyst_runner_reaches_graph_compilation_boundary() -> None:
    source = await anyio.Path(_CATALYST_WORKFLOW).read_text(encoding="utf-8")

    with pytest.raises(ValueError) as raised:
        run_workflow.compile_workflow(source)

    assert str(raised.value) == "example contains assertions that the graph compiler cannot execute"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("executor_kind", "instruction"),
    [
        ("Agent", "./instructions/missing-agent.md"),
        ("Program", "./instructions/missing-program.md"),
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
        workflow_path=os.path.join(_FIXTURES_DIR, "dispatch.workflow"),
        request="Do the work.",
        complete=complete,
    )

    assert result == {"result": "completed"}
    assert prompts[0].splitlines()[0] == f"Instruction: {instruction}"
    assert f'"{instruction}"' not in prompts[0]


@pytest.mark.anyio
async def test_human_executor_receives_utf8_instruction_contents() -> None:
    instruction_path = "./instructions/human.md"
    expected = await anyio.Path(os.path.join(_FIXTURES_DIR, "instructions", "human.md")).read_text(encoding="utf-8")
    prompts: list[str] = []

    async def complete(prompt: str) -> str:
        prompts.append(prompt)
        return "confirmed"

    result = await run_workflow.execute_workflow(
        _dispatch_workflow("Human", instruction_path),
        workflow_path=os.path.join(_FIXTURES_DIR, "human.workflow"),
        request="请核对。",
        complete=complete,
    )

    assert result == {"result": "confirmed"}
    assert f"Instruction: {expected}" in prompts[0]
    assert instruction_path not in prompts[0]


@pytest.mark.anyio
async def test_human_instruction_rejects_missing_file(tmp_path: object) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        await run_workflow._read_human_instruction(
            os.path.join(str(tmp_path), "missing.workflow"),
            "./missing.md",
        )


@pytest.mark.anyio
async def test_human_instruction_dispatch_error_identifies_step_and_path(tmp_path: object) -> None:
    instruction_path = "./missing.md"
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
    tmp_path: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instruction_path = "./private.md"
    physical_path = os.path.join(str(tmp_path), "credentials", "private.md")

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
    instruction_path = os.path.join(str(tmp_path), "empty.md")
    await anyio.Path(instruction_path).write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="must not be empty"):
        await run_workflow._read_human_instruction(
            os.path.join(str(tmp_path), "empty.workflow"),
            "./empty.md",
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "instruction_path",
    [
        "/absolute/instruction.md",
        "C:/instruction.md",
        r"\\server\share\instruction.md",
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
            "./instructions/../secret.md",
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
    instruction_path = os.path.join(str(tmp_path), "invalid.md")
    await anyio.Path(instruction_path).write_bytes(b"\xff")

    with pytest.raises(ValueError, match="UTF-8"):
        await run_workflow._read_human_instruction(
            os.path.join(str(tmp_path), "invalid.workflow"),
            "./invalid.md",
        )


@pytest.mark.anyio
async def test_human_instruction_rejects_symlink_escape(tmp_path: object) -> None:
    workflow_dir = os.path.join(str(tmp_path), "workflow")
    await anyio.Path(workflow_dir).mkdir()
    outside_path = os.path.join(str(tmp_path), "outside.md")
    await anyio.Path(outside_path).write_text("outside", encoding="utf-8")
    link_path = os.path.join(workflow_dir, "link.md")
    try:
        await anyio.Path(link_path).symlink_to(outside_path)
    except OSError as error:
        pytest.skip(f"symlink creation denied: {error}")

    with pytest.raises(ValueError, match="escapes"):
        await run_workflow._read_human_instruction(
            os.path.join(workflow_dir, "escape.workflow"),
            "./link.md",
        )


@pytest.mark.anyio
async def test_human_instruction_requires_workflow_path(tmp_path: object) -> None:
    with pytest.raises(ValueError, match=r"\.workflow"):
        await run_workflow._read_human_instruction(
            os.path.join(str(tmp_path), "workflow.txt"),
            "./missing.md",
        )
