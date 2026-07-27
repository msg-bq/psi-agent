from __future__ import annotations

import importlib.util
import os
import sys
from typing import Any, cast

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


def _dispatch_workflow(
    executor_kind: str | None,
    instruction: str,
    *,
    input_ids: tuple[str, ...] = ("request",),
    output_ids: tuple[str, ...] = ("result",),
) -> str:
    executor_declaration = "" if executor_kind is None else f"const worker: {executor_kind}, Executor;"
    input_declarations = "\n".join(f"const {artifact_id}: Artifact;" for artifact_id in input_ids)
    output_declarations = "\n".join(f"const {artifact_id}: Artifact;" for artifact_id in output_ids)
    inputs = ", ".join(input_ids)
    outputs = ", ".join(output_ids)
    return f"""
const dispatch: Workflow;
const dispatch_step: Step;
const dispatch_name: StepName;
{executor_declaration}
{input_declarations}
{output_declarations}

workflow dispatch {{
    input_workflow(dispatch) == [{inputs}];
    output_workflow(dispatch) == [{outputs}];
    step_name(dispatch_step) == dispatch_name;
    step_instruction(dispatch_step) == "{instruction}";
    step_executor(dispatch_step) == worker;
    consumes(dispatch_step) == [{inputs}];
    produces(dispatch_step) == [{outputs}];
}}
"""


def test_executor_superconcept_is_recognized() -> None:
    compiled = run_workflow.compile_workflow(_dispatch_workflow("Agent", "summarize_request"))

    assert compiled.executor_kinds["worker"] == "Agent"


@pytest.mark.anyio
async def test_in_memory_workflow_compiles_and_executes() -> None:
    prompts: list[str] = []

    async def complete(prompt: str) -> str:
        prompts.append(prompt)
        return "completed"

    result = await run_workflow.execute_workflow(
        _dispatch_workflow("Agent", "summarize_request"),
        request="Explain structured concurrency.",
        complete=complete,
    )

    assert result == {"result": "completed"}
    assert prompts[0].splitlines()[0] == "Instruction: summarize_request"


@pytest.mark.anyio
async def test_multiple_inputs_and_outputs_use_artifact_id_mapping() -> None:
    prompts: list[str] = []

    async def complete(prompt: str) -> object:
        prompts.append(prompt)
        return {"details": {"count": 2}, "summary": "combined"}

    result = await run_workflow.execute_workflow(
        _dispatch_workflow(
            "Agent",
            "combine_inputs",
            input_ids=("left", "right"),
            output_ids=("summary", "details"),
        ),
        inputs={"left": "alpha", "right": "beta"},
        complete=complete,
    )

    assert result == {"details": {"count": 2}, "summary": "combined"}
    assert '"left": "alpha"' in prompts[0]
    assert '"right": "beta"' in prompts[0]
    assert '["details", "summary"]' in prompts[0]


@pytest.mark.anyio
async def test_multiple_outputs_must_match_declared_artifact_ids() -> None:
    async def complete(prompt: str) -> object:
        del prompt
        return {"summary": "missing details"}

    with pytest.RaisesGroup(pytest.RaisesExc(ValueError, match="must match exactly")):
        await run_workflow.execute_workflow(
            _dispatch_workflow(
                "Agent",
                "combine_inputs",
                output_ids=("summary", "details"),
            ),
            request="source",
            complete=complete,
        )


@pytest.mark.anyio
async def test_multiple_outputs_require_artifact_id_mapping() -> None:
    async def complete(prompt: str) -> object:
        del prompt
        return "one positional value"

    with pytest.RaisesGroup(pytest.RaisesExc(ValueError, match="result must be a mapping")):
        await run_workflow.execute_workflow(
            _dispatch_workflow(
                "Agent",
                "combine_inputs",
                output_ids=("summary", "details"),
            ),
            request="source",
            complete=complete,
        )


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
        request="Do the work.",
        complete=complete,
    )

    assert result == {"result": "completed"}
    assert prompts[0].splitlines()[0] == f"Instruction: {instruction}"
    assert f'"{instruction}"' not in prompts[0]


@pytest.mark.anyio
async def test_untyped_executor_defaults_to_agent() -> None:
    prompts: list[str] = []

    async def complete(prompt: str) -> str:
        prompts.append(prompt)
        return "completed"

    instruction = "./instructions/untyped-agent.txt"
    result = await run_workflow.execute_workflow(
        _dispatch_workflow(None, instruction),
        request="Do the work.",
        complete=complete,
    )

    assert result == {"result": "completed"}
    assert prompts[0].splitlines()[0] == f"Instruction: {instruction}"


@pytest.mark.anyio
async def test_human_instruction_reference_is_opaque_to_runner() -> None:
    preparation_prompts: list[str] = []
    human_prompts: list[str] = []

    async def complete(prompt: str) -> str:
        pytest.fail(f"ordinary completion called with {prompt!r}")

    async def prepare_human_instruction(prompt: str) -> str:
        preparation_prompts.append(prompt)
        return "Review the supplied proposal and answer approve or reject."

    async def request_human(prompt: str) -> object:
        human_prompts.append(prompt)
        return {"decision": "approve"}

    result = await run_workflow.execute_workflow(
        _dispatch_workflow("Human", "./instructions/../proposal.txt"),
        request="proposal-v2",
        complete=complete,
        prepare_human_instruction=prepare_human_instruction,
        request_human=request_human,
    )

    assert result == {"result": {"decision": "approve"}}
    assert len(preparation_prompts) == 1
    assert "Step: dispatch_step" in preparation_prompts[0]
    assert "Instruction or reference: ./instructions/../proposal.txt" in preparation_prompts[0]
    assert '"request": "proposal-v2"' in preparation_prompts[0]
    assert "runner does not resolve or constrain paths" in preparation_prompts[0]
    assert "available tools and normal approval flow" in preparation_prompts[0]
    assert human_prompts == ["Review the supplied proposal and answer approve or reject."]


@pytest.mark.anyio
async def test_human_step_can_return_multiple_artifacts() -> None:
    preparation_prompts: list[str] = []

    async def complete(prompt: str) -> str:
        pytest.fail(f"ordinary completion called with {prompt!r}")

    async def prepare_human_instruction(prompt: str) -> str:
        preparation_prompts.append(prompt)
        return "Provide the decision and rationale."

    async def request_human(prompt: str) -> object:
        assert prompt == "Provide the decision and rationale."
        return {"decision": "approve", "rationale": "requirements met"}

    result = await run_workflow.execute_workflow(
        _dispatch_workflow(
            "Human",
            "./review/reference.txt",
            output_ids=("decision", "rationale"),
        ),
        request="proposal-v3",
        complete=complete,
        prepare_human_instruction=prepare_human_instruction,
        request_human=request_human,
    )

    assert result == {"decision": "approve", "rationale": "requirements met"}
    assert '["decision", "rationale"]' in preparation_prompts[0]


@pytest.mark.anyio
async def test_human_preparation_failure_does_not_request_human() -> None:
    async def complete(prompt: str) -> str:
        pytest.fail(f"ordinary completion called with {prompt!r}")

    async def prepare_human_instruction(prompt: str) -> str:
        del prompt
        raise PermissionError("resource access was not approved")

    async def request_human(prompt: str) -> str:
        pytest.fail(f"human called with {prompt!r}")

    with pytest.RaisesGroup(pytest.RaisesExc(PermissionError, match="not approved")):
        await run_workflow.execute_workflow(
            _dispatch_workflow("Human", "./private/reference.txt"),
            request="review",
            complete=complete,
            prepare_human_instruction=prepare_human_instruction,
            request_human=request_human,
        )


@pytest.mark.anyio
async def test_human_preparation_must_return_text() -> None:
    async def complete(prompt: str) -> str:
        pytest.fail(f"ordinary completion called with {prompt!r}")

    async def prepare_human_instruction(prompt: str) -> str:
        del prompt
        return "  "

    async def request_human(prompt: str) -> str:
        pytest.fail(f"human called with {prompt!r}")

    with pytest.RaisesGroup(pytest.RaisesExc(ValueError, match="preparation returned no text")):
        await run_workflow.execute_workflow(
            _dispatch_workflow("Human", "review_reference"),
            request="review",
            complete=complete,
            prepare_human_instruction=prepare_human_instruction,
            request_human=request_human,
        )


@pytest.mark.anyio
async def test_human_step_requires_preparer_and_requester() -> None:
    async def complete(prompt: str) -> str:
        pytest.fail(f"ordinary completion called with {prompt!r}")

    with pytest.RaisesGroup(pytest.RaisesExc(ValueError, match="requires prepare_human_instruction and request_human")):
        await run_workflow.execute_workflow(
            _dispatch_workflow("Human", "review_reference"),
            request="review",
            complete=complete,
        )
