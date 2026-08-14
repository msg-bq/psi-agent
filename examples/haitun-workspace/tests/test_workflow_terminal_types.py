"""TerminalStep and BoolArtifact catalog/lowering contracts."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_SKILL_ROOT = WORKSPACE_ROOT / "skills" / "workflow"
if str(WORKFLOW_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKFLOW_SKILL_ROOT))

from fusion_flow.workflow_execution import DispatchContext  # noqa: E402
from fusion_flow.workflow_graph import ProducesEdge  # noqa: E402
from fusion_flow.workflow_runner import (  # noqa: E402
    ProgramInvocation,
    _build_dispatch,
    _normalize_program_stdout,
    _normalize_terminal_output,
    compile_workflow,
)


def _source(*, declaration: str, produces: str = "") -> str:
    return f"""
const delta: Artifact;
{declaration}
const check_convergence: TerminalStep;
const predicate_agent: Agent;

workflow convergence {{
    input_workflow(convergence) == [delta];
    consumes(check_convergence) == [delta];
    {produces}
    step_name(check_convergence) == "Check convergence";
    step_instruction(check_convergence) == "Return only the terminal predicate.";
    step_executor(check_convergence) == predicate_agent;
    output_workflow(convergence) == [delta];
}}
"""


def test_terminal_step_accepts_step_operators_and_preserves_explicit_roles() -> None:
    compiled = compile_workflow(
        _source(
            declaration="const done: BoolArtifact;",
            produces="produces(check_convergence) == [done];",
        )
    )

    step = next(step for step in compiled.graph.steps if step.step_id == "check_convergence")
    done = next(artifact for artifact in compiled.graph.artifacts if artifact.artifact_id == "done")
    assert step.step_type == "TerminalStep"
    assert done.artifact_type == "BoolArtifact"
    assert ProducesEdge(step_id="check_convergence", artifact_id="done") in compiled.graph.edges
    assert compiled.graph.to_dict()["steps"][0]["step_type"] == "TerminalStep"


def test_terminal_step_omitted_produces_gets_one_implicit_bool_output() -> None:
    compiled = compile_workflow(_source(declaration=""))

    outputs = [
        edge.artifact_id
        for edge in compiled.graph.edges
        if isinstance(edge, ProducesEdge) and edge.step_id == "check_convergence"
    ]
    assert outputs == ["$fusion_flow/terminal/check_convergence/done"]
    implicit = next(artifact for artifact in compiled.graph.artifacts if artifact.artifact_id == outputs[0])
    assert implicit.artifact_type == "BoolArtifact"


def test_bool_artifact_role_survives_a_selector_condition() -> None:
    compiled = compile_workflow(
        """
const predicate: BoolArtifact;
const left: Artifact;
const right: Artifact;
const selected: Artifact;

workflow selection {
    input_workflow(selection) == [predicate, left, right];
    selected == if(predicate = True, left, right);
    output_workflow(selection) == [selected];
}
"""
    )

    predicate = next(artifact for artifact in compiled.graph.artifacts if artifact.artifact_id == "predicate")
    assert predicate.artifact_type == "BoolArtifact"


@pytest.mark.parametrize(
    ("declaration", "produces"),
    [
        ("const done: Artifact;", "produces(check_convergence) == [done];"),
        ("const done: BoolArtifact;", "produces(check_convergence) == [];"),
        (
            "const done: BoolArtifact;\nconst detail: Artifact;",
            "produces(check_convergence) == [done, detail];",
        ),
    ],
)
def test_terminal_step_rejects_non_bool_empty_or_multiple_outputs(
    declaration: str,
    produces: str,
) -> None:
    with pytest.raises(ValueError, match=r"must produce exactly one BoolArtifact|must be declared as BoolArtifact"):
        compile_workflow(_source(declaration=declaration, produces=produces))


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (True, {"done": True}),
        (False, {"done": False}),
        ({"done": True}, {"done": True}),
    ],
)
def test_terminal_dispatch_accepts_raw_or_named_strict_bool(
    result: object,
    expected: dict[str, object],
) -> None:
    assert _normalize_terminal_output("terminal", ("done",), result) == expected


@pytest.mark.parametrize("result", [0, 1, "true", None, {"done": 1}])
def test_terminal_dispatch_rejects_truthy_and_falsy_coercions(result: object) -> None:
    with pytest.raises(ValueError, match="strict Boolean"):
        _normalize_terminal_output("terminal", ("done",), result)


def test_terminal_program_stdout_parses_json_boolean_without_internal_output_key() -> None:
    assert _normalize_program_stdout("terminal", ("done",), "true\n", terminal=True) == {"done": True}
    with pytest.raises(ValueError, match="strict Boolean"):
        _normalize_program_stdout("terminal", ("done",), "1\n", terminal=True)


@pytest.mark.anyio
async def test_terminal_program_invocation_carries_strict_boolean_contract() -> None:
    compiled = compile_workflow(
        """
const seed: Artifact;
const done: BoolArtifact;
const terminal: TerminalStep;
const predicate: Program, Executor;

workflow predicate_flow {
    input_workflow(predicate_flow) == [seed];
    consumes(terminal) == [seed];
    produces(terminal) == [done];
    step_name(terminal) == "Terminal";
    step_instruction(terminal) == "Return strict JSON true or false.";
    step_executor(terminal) == predicate;
    program_path(predicate) == "predicate.py";
    output_workflow(predicate_flow) == [seed];
}
"""
    )
    seen: list[ProgramInvocation] = []

    async def run_program(invocation: ProgramInvocation) -> dict[str, object]:
        seen.append(invocation)
        return {invocation.output_ids[0]: True}

    dispatch = _build_dispatch(
        compiled,
        instructions={"terminal": "Return strict JSON true or false."},
        program_paths={"predicate": "predicate.py"},
        work_dir=WORKSPACE_ROOT,
        complete=None,
        run_program=run_program,
        prepare_human_instruction=None,
        request_human=None,
    )
    step = compiled.graph.steps[0]

    result = await dispatch(step, {"seed": 0}, DispatchContext())

    assert result == {"done": True}
    assert len(seen) == 1
    assert seen[0].terminal is True
