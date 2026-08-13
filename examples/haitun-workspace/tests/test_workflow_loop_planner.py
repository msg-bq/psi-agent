"""Declarative feedback discovery from FusionFlow source and graph topology."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_SKILL_ROOT = WORKSPACE_ROOT / "skills" / "workflow"
WORKFLOW_EXAMPLES_ROOT = WORKFLOW_SKILL_ROOT / "examples"
if str(WORKFLOW_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKFLOW_SKILL_ROOT))

from fusion_flow.workflow_execution import (  # noqa: E402
    DispatchContext,
    ExecutionPlanError,
    execute_plan,
    generate_plan,
)
from fusion_flow.workflow_graph import (  # noqa: E402
    ArtifactNode,
    ConsumesEdge,
    ProducesEdge,
    StepNode,
    WorkflowGraph,
)
from fusion_flow.workflow_runner import CompletionContext, compile_workflow, execute_workflow  # noqa: E402

COUNTER_SOURCE = """
const counter: Workflow;
const state: Artifact;
const candidate: Artifact;
const done: BoolArtifact;

const propose: Step;
const advance: Step;
const terminal: TerminalStep;
const worker: Agent;

workflow counter {
    input_workflow(counter) == [state];

    consumes(propose) == [state];
    produces(propose) == [candidate];

    consumes(advance) == [state, candidate];
    produces(advance) == [state];

    consumes(terminal) == [candidate];
    produces(terminal) == [done];

    output_workflow(counter) == [state];

    step_name(propose) == "Propose";
    step_instruction(propose) == "Propose the next integer.";
    step_executor(propose) == worker;

    step_name(advance) == "Advance";
    step_instruction(advance) == "Commit the proposed integer.";
    step_executor(advance) == worker;

    step_name(terminal) == "Terminal";
    step_instruction(terminal) == "Return true when candidate is at least three.";
    step_executor(terminal) == worker;
}
"""

IMPLICIT_COUNTER_SOURCE = """
const state: Artifact;
const candidate: Artifact;

const propose: Step;
const advance: Step;
const terminal: TerminalStep;
const worker: Agent;

workflow counter {
    input_workflow(counter) == [state];

    consumes(propose) == [state];
    produces(propose) == [candidate];

    consumes(advance) == [state, candidate];
    produces(advance) == [state];

    consumes(terminal) == [candidate];

    output_workflow(counter) == [state];

    step_name(propose) == "Propose";
    step_instruction(propose) == "Propose the next integer.";
    step_executor(propose) == worker;

    step_name(advance) == "Advance";
    step_instruction(advance) == "Commit the proposed integer.";
    step_executor(advance) == worker;

    step_name(terminal) == "Terminal";
    step_instruction(terminal) == "Return true when candidate is at least three.";
    step_executor(terminal) == worker;
}
"""


def _int_value(values: Mapping[str, object], artifact_id: str) -> int:
    value = values[artifact_id]
    assert type(value) is int
    return value


@pytest.mark.anyio
async def test_g4_feedback_source_plans_and_executes_until_final_next_state() -> None:
    graph = compile_workflow(COUNTER_SOURCE).graph
    plan = generate_plan(graph)

    assert plan.fibers == ()
    assert len(plan.loops) == 1
    loop = plan.loops[0]
    assert loop.feedback_artifact_ids == ("state",)
    assert loop.step_ids == ("advance", "propose", "terminal")
    assert loop.terminal_step_id == "terminal"
    seen_states: list[int] = []

    async def dispatch(
        step: StepNode,
        inputs: Mapping[str, object],
        context: DispatchContext,
    ) -> Mapping[str, object]:
        assert context.loop_id == "terminal"
        if step.step_id == "propose":
            state = _int_value(inputs, "state")
            seen_states.append(state)
            return {"candidate": state + 1}
        if step.step_id == "advance":
            return {"state": inputs["candidate"]}
        return {"done": _int_value(inputs, "candidate") >= 3}

    outputs = await execute_plan(
        plan,
        graph,
        inputs={"state": 0},
        dispatch=dispatch,
        max_loop_epochs=5,
    )

    assert outputs == {"state": 3}
    assert seen_states == [0, 1, 2]


@pytest.mark.anyio
async def test_runner_executes_implicit_terminal_raw_bool_until_three_epochs() -> None:
    seen_states: list[int] = []
    implicit_output_ids: list[tuple[str, ...]] = []

    async def complete(prompt: str, context: CompletionContext) -> object:
        del prompt
        if context.step_id == "propose":
            state = _int_value(context.inputs, "state")
            seen_states.append(state)
            return {"candidate": state + 1}
        if context.step_id == "advance":
            return {"state": context.inputs["candidate"]}
        implicit_output_ids.append(context.output_ids)
        return _int_value(context.inputs, "candidate") >= 3

    outputs = await execute_workflow(
        IMPLICIT_COUNTER_SOURCE,
        inputs={"state": 0},
        complete=complete,
        max_loop_epochs=5,
    )

    assert outputs == {"state": 3}
    assert seen_states == [0, 1, 2]
    assert implicit_output_ids == [
        ("$fusion_flow/terminal/terminal/done",),
        ("$fusion_flow/terminal/terminal/done",),
        ("$fusion_flow/terminal/terminal/done",),
    ]


def test_cycle_without_terminal_step_is_rejected_instead_of_assumed_to_be_a_loop() -> None:
    graph = WorkflowGraph(
        workflow_id="accidental",
        steps=(StepNode("update", "Update", "worker"),),
        artifacts=(ArtifactNode("state", is_input=True, is_output=True),),
        edges=(ConsumesEdge("state", "update"), ProducesEdge("update", "state")),
    )

    with pytest.raises(ExecutionPlanError, match="MISSING_TERMINAL_STEP"):
        generate_plan(graph)


def test_feedback_cycle_without_workflow_input_seed_is_rejected() -> None:
    graph = WorkflowGraph(
        workflow_id="unseeded",
        steps=(
            StepNode("update", "Update", "worker"),
            StepNode("terminal", "Terminal", "worker", step_type="TerminalStep"),
        ),
        artifacts=(
            ArtifactNode("state", is_output=True),
            ArtifactNode("done", artifact_type="BoolArtifact"),
        ),
        edges=(
            ConsumesEdge("state", "update"),
            ProducesEdge("update", "state"),
            ConsumesEdge("state", "terminal"),
            ProducesEdge("terminal", "done"),
        ),
    )

    with pytest.raises(ExecutionPlanError, match="MISSING_INITIAL_STATE"):
        generate_plan(graph)


def test_multiple_feedback_components_fail_closed() -> None:
    graph = WorkflowGraph(
        workflow_id="two_loops",
        steps=(
            StepNode("update_a", "Update A", "worker"),
            StepNode("update_b", "Update B", "worker"),
            StepNode("terminal", "Terminal", "worker", step_type="TerminalStep"),
        ),
        artifacts=(
            ArtifactNode("a", is_input=True, is_output=True),
            ArtifactNode("b", is_input=True, is_output=True),
            ArtifactNode("done", artifact_type="BoolArtifact"),
        ),
        edges=(
            ConsumesEdge("a", "update_a"),
            ProducesEdge("update_a", "a"),
            ConsumesEdge("b", "update_b"),
            ProducesEdge("update_b", "b"),
            ConsumesEdge("a", "terminal"),
            ConsumesEdge("b", "terminal"),
            ProducesEdge("terminal", "done"),
        ),
    )

    with pytest.raises(ExecutionPlanError, match="MULTIPLE_FEEDBACK_COMPONENTS"):
        generate_plan(graph)


def test_terminal_step_must_depend_on_the_feedback_component() -> None:
    graph = WorkflowGraph(
        workflow_id="detached",
        steps=(
            StepNode("update", "Update", "worker"),
            StepNode("terminal", "Terminal", "worker", step_type="TerminalStep"),
        ),
        artifacts=(
            ArtifactNode("state", is_input=True, is_output=True),
            ArtifactNode("seed", is_input=True),
            ArtifactNode("done", artifact_type="BoolArtifact"),
        ),
        edges=(
            ConsumesEdge("state", "update"),
            ProducesEdge("update", "state"),
            ConsumesEdge("seed", "terminal"),
            ProducesEdge("terminal", "done"),
        ),
    )

    with pytest.raises(ExecutionPlanError, match="TERMINAL_LOOP_NOT_FOUND"):
        generate_plan(graph)


def test_cycle_remaining_inside_one_epoch_is_reported_as_version_ambiguity() -> None:
    graph = WorkflowGraph(
        workflow_id="ambiguous",
        steps=(
            StepNode("a", "A", "worker"),
            StepNode("b", "B", "worker"),
            StepNode("terminal", "Terminal", "worker", step_type="TerminalStep"),
        ),
        artifacts=(
            ArtifactNode("state", is_input=True, is_output=True),
            ArtifactNode("x"),
            ArtifactNode("y"),
            ArtifactNode("done", artifact_type="BoolArtifact"),
        ),
        edges=(
            ConsumesEdge("state", "a"),
            ConsumesEdge("y", "a"),
            ProducesEdge("a", "x"),
            ConsumesEdge("x", "b"),
            ProducesEdge("b", "y"),
            ProducesEdge("b", "state"),
            ConsumesEdge("x", "terminal"),
            ProducesEdge("terminal", "done"),
        ),
    )

    with pytest.raises(ExecutionPlanError, match="RESIDUAL_EPOCH_CYCLE"):
        generate_plan(graph)


@pytest.mark.parametrize(
    ("filename", "feedback_artifact_id", "terminal_step_id", "outside_step_ids"),
    (
        ("loop_engineering.workflow", "engineering_state", "terminal_step", ()),
        ("react_loop.workflow", "react_state", "terminal_step", ("extract_answer_step",)),
    ),
)
def test_reference_feedback_workflow_compiles_to_expected_loop_region(
    filename: str,
    feedback_artifact_id: str,
    terminal_step_id: str,
    outside_step_ids: tuple[str, ...],
) -> None:
    source = (WORKFLOW_EXAMPLES_ROOT / filename).read_text(encoding="utf-8")

    graph = compile_workflow(source).graph
    plan = generate_plan(graph)

    assert len(plan.loops) == 1
    loop = plan.loops[0]
    assert loop.feedback_artifact_ids == (feedback_artifact_id,)
    assert loop.terminal_step_id == terminal_step_id
    assert tuple(fiber.fiber_id for fiber in plan.fibers) == outside_step_ids
