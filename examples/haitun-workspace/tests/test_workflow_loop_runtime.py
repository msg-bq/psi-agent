"""Epoch snapshot, barrier, termination, and visibility runtime contracts."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import cast

import anyio
import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_SKILL_ROOT = WORKSPACE_ROOT / "skills" / "workflow"
WORKFLOW_EXAMPLES_ROOT = WORKFLOW_SKILL_ROOT / "examples"
if str(WORKFLOW_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKFLOW_SKILL_ROOT))

from fusion_flow.artifact_store import ArtifactStore  # noqa: E402
from fusion_flow.job_store import HumanWorkflowRun, _run_from_json, _run_to_json  # noqa: E402
from fusion_flow.step_timing import StepTiming, StepTimingMetadata  # noqa: E402
from fusion_flow.workflow_execution import (  # noqa: E402
    Await,
    DispatchContext,
    ExecutionCheckpoint,
    ExecutionPlan,
    ExecutionPlanError,
    Fiber,
    Invoke,
    LoopExecutionCheckpoint,
    LoopRegionPlan,
    StepOutputError,
    create_execution_checkpoint,
    execute_plan,
)
from fusion_flow.workflow_graph import (  # noqa: E402
    ArtifactNode,
    ConsumesEdge,
    ProducesEdge,
    StepNode,
    WorkflowGraph,
)
from fusion_flow.workflow_runner import (  # noqa: E402
    CompletionContext,
    ProgramInvocation,
    execute_workflow,
)


def _step(step_id: str, *, terminal: bool = False) -> StepNode:
    return StepNode(
        step_id=step_id,
        name_id=step_id,
        executor_id=f"{step_id}_executor",
        step_type="TerminalStep" if terminal else "Step",
    )


def _int_value(values: Mapping[str, object], artifact_id: str) -> int:
    value = values[artifact_id]
    assert type(value) is int
    return value


def _counter_graph() -> tuple[WorkflowGraph, ExecutionPlan]:
    graph = WorkflowGraph(
        workflow_id="counter",
        steps=(
            _step("propose"),
            _step("advance"),
            _step("terminal", terminal=True),
            _step("outside"),
        ),
        artifacts=(
            ArtifactNode("state", is_input=True, is_output=True),
            ArtifactNode("candidate"),
            ArtifactNode("done", artifact_type="BoolArtifact"),
            ArtifactNode("observed", is_output=True),
        ),
        edges=(
            ConsumesEdge("state", "propose"),
            ProducesEdge("propose", "candidate"),
            ConsumesEdge("state", "advance"),
            ConsumesEdge("candidate", "advance"),
            ProducesEdge("advance", "state"),
            ConsumesEdge("candidate", "terminal"),
            ProducesEdge("terminal", "done"),
            ConsumesEdge("state", "outside"),
            ProducesEdge("outside", "observed"),
        ),
    )
    loop = LoopRegionPlan(
        loop_id="terminal",
        feedback_artifact_ids=("state",),
        step_ids=("advance", "propose", "terminal"),
        terminal_step_id="terminal",
        terminal_output_artifact_id="done",
        fibers=(
            Fiber("propose", (Invoke("propose"),)),
            Fiber("advance", (Await(("propose",)), Invoke("advance"))),
            Fiber("terminal", (Await(("propose",)), Invoke("terminal"))),
        ),
    )
    return graph, ExecutionPlan(
        workflow_id="counter",
        fibers=(Fiber("outside", (Await(("advance",)), Invoke("outside"))),),
        loops=(loop,),
    )


async def _unexpected_dispatch(
    step: StepNode,
    inputs: Mapping[str, object],
    context: DispatchContext,
) -> Mapping[str, object]:
    del step, inputs, context
    raise AssertionError("invalid checkpoint must fail before dispatch")


@pytest.mark.anyio
async def test_loop_commits_next_state_before_termination_and_hides_intermediate_epochs() -> None:
    graph, plan = _counter_graph()
    proposed_from: list[int] = []
    outside_seen: list[int] = []
    contexts: list[DispatchContext] = []

    async def dispatch(
        step: StepNode,
        inputs: Mapping[str, object],
        context: DispatchContext,
    ) -> Mapping[str, object]:
        contexts.append(context)
        if step.step_id == "propose":
            state = _int_value(inputs, "state")
            proposed_from.append(state)
            return {"candidate": state + 1}
        if step.step_id == "advance":
            return {"state": inputs["candidate"]}
        if step.step_id == "terminal":
            return {"done": _int_value(inputs, "candidate") >= 3}
        state = _int_value(inputs, "state")
        outside_seen.append(state)
        return {"observed": state}

    outputs = await execute_plan(plan, graph, inputs={"state": 0}, dispatch=dispatch)

    assert outputs == {"state": 3, "observed": 3}
    assert proposed_from == [0, 1, 2]
    assert outside_seen == [3]
    loop_contexts = [context for context in contexts if context.loop_id == "terminal"]
    assert {context.epoch for context in loop_contexts} == {0, 1, 2}
    assert all(context.invocation_id.startswith("terminal@") for context in loop_contexts)


@pytest.mark.anyio
async def test_reference_react_loop_executes_to_final_action() -> None:
    source = await anyio.Path(WORKFLOW_EXAMPLES_ROOT / "react_loop.workflow").read_text(encoding="utf-8")

    async def complete(prompt: str, context: CompletionContext) -> object:
        del prompt
        if context.step_id == "reason":
            prompt_value = _int_value(context.inputs, "prompt")
            return {"thought": f"thought-{prompt_value}", "action": prompt_value + 1}
        if context.step_id == "env_step":
            action = _int_value(context.inputs, "action")
            return {"observation": f"observation-{action}", "done": action >= 3}
        if context.step_id == "update":
            return {"prompt": context.inputs["action"]}
        raise AssertionError(f"unexpected Agent step: {context.step_id}")

    async def run_program(invocation: ProgramInvocation) -> str:
        assert invocation.name == "terminal_validator"
        assert invocation.argv == ("./skills/workflow/examples/terminal_identity.py",)
        assert invocation.cwd == WORKSPACE_ROOT
        assert invocation.binding_name == "terminal"
        assert invocation.output_ids == ("loop_done",)
        assert invocation.terminal is True
        assert type(invocation.inputs["done"]) is bool
        program_path = WORKSPACE_ROOT / invocation.argv[0]
        result = await anyio.run_process(
            [sys.executable, str(program_path)],
            input=invocation.stdin.encode(),
        )
        return result.stdout.decode()

    outputs = await execute_workflow(
        source,
        inputs={"prompt": 0},
        complete=complete,
        work_dir=WORKSPACE_ROOT,
        run_program=run_program,
        max_loop_epochs=5,
    )

    assert outputs == {"action": 3}


@pytest.mark.anyio
async def test_reference_loop_engineering_executes_to_committed_state() -> None:
    source = await anyio.Path(WORKFLOW_EXAMPLES_ROOT / "loop_engineering.workflow").read_text(encoding="utf-8")

    async def complete(prompt: str, context: CompletionContext) -> object:
        del prompt
        if context.step_id == "discover":
            return {"work": _int_value(context.inputs, "state") + 1}
        if context.step_id == "engineer":
            return {"candidate": context.inputs["work"]}
        if context.step_id == "verify":
            return {"verification": context.inputs["candidate"]}
        if context.step_id == "advance":
            return {"next_state": context.inputs["candidate"]}
        if context.step_id == "should_stop":
            return _int_value(context.inputs, "verification") >= 3
        if context.step_id == "commit":
            return {"state": context.inputs["next_state"]}
        raise AssertionError(f"unexpected Agent step: {context.step_id}")

    outputs = await execute_workflow(
        source,
        inputs={"state": 0},
        complete=complete,
        max_loop_epochs=5,
    )

    assert outputs == {"state": 3}


@pytest.mark.anyio
async def test_loop_records_each_epoch_and_retry_attempt_timing() -> None:
    graph, plan = _counter_graph()
    graph = WorkflowGraph(
        workflow_id=graph.workflow_id,
        steps=tuple(replace(step, max_attempts=2) if step.step_id == "propose" else step for step in graph.steps),
        artifacts=graph.artifacts,
        edges=graph.edges,
        policy=graph.policy,
        selectors=graph.selectors,
    )
    timings: list[StepTiming] = []
    failed_first_attempt = False

    async def dispatch(
        step: StepNode,
        inputs: Mapping[str, object],
        context: DispatchContext,
    ) -> Mapping[str, object]:
        nonlocal failed_first_attempt
        if step.step_id == "propose":
            if context.epoch == 0 and context.attempt == 1 and not failed_first_attempt:
                failed_first_attempt = True
                raise RuntimeError("retry once")
            return {"candidate": _int_value(inputs, "state") + 1}
        if step.step_id == "advance":
            return {"state": inputs["candidate"]}
        if step.step_id == "terminal":
            return {"done": _int_value(inputs, "candidate") >= 2}
        return {"observed": inputs["state"]}

    outputs = await execute_plan(
        plan,
        graph,
        inputs={"state": 0},
        dispatch=dispatch,
        timing_recorder=timings.append,
        timing_metadata={
            "propose": StepTimingMetadata(
                step_name="propose",
                executor_id="propose_executor",
                executor_kind="Program",
            )
        },
    )

    assert outputs == {"state": 2, "observed": 2}
    assert [timing.step_id for timing in timings] == [
        "terminal@0/propose",
        "terminal@1/propose",
    ]
    assert [attempt.status for attempt in timings[0].attempts] == ["error", "ok"]
    assert [attempt.attempt for attempt in timings[0].attempts] == [1, 2]
    assert [attempt.status for attempt in timings[1].attempts] == ["ok"]


@pytest.mark.anyio
async def test_top_level_plan_must_await_real_loop_dependency() -> None:
    graph, plan = _counter_graph()
    invalid_plan = ExecutionPlan(
        workflow_id=plan.workflow_id,
        fibers=(Fiber("outside", (Invoke("outside"),)),),
        loops=plan.loops,
    )

    with pytest.raises(ExecutionPlanError, match=r"missing dependencies for outside.*advance"):
        await execute_plan(
            invalid_plan,
            graph,
            inputs={"state": 0},
            dispatch=_unexpected_dispatch,
        )


@pytest.mark.anyio
async def test_loop_epoch_plan_must_await_non_feedback_dependency() -> None:
    graph, plan = _counter_graph()
    loop = plan.loops[0]
    invalid_loop = LoopRegionPlan(
        loop_id=loop.loop_id,
        feedback_artifact_ids=loop.feedback_artifact_ids,
        step_ids=loop.step_ids,
        terminal_step_id=loop.terminal_step_id,
        terminal_output_artifact_id=loop.terminal_output_artifact_id,
        fibers=tuple(Fiber(step_id, (Invoke(step_id),)) for step_id in ("propose", "advance", "terminal")),
    )
    invalid_plan = ExecutionPlan(
        workflow_id=plan.workflow_id,
        fibers=plan.fibers,
        loops=(invalid_loop,),
    )

    with pytest.raises(ExecutionPlanError, match=r"missing dependencies for (advance|terminal).*propose"):
        await execute_plan(
            invalid_plan,
            graph,
            inputs={"state": 0},
            dispatch=_unexpected_dispatch,
        )


@pytest.mark.anyio
async def test_loop_plan_rejects_circular_waits_before_dispatch() -> None:
    graph, plan = _counter_graph()
    loop = plan.loops[0]
    invalid_loop = LoopRegionPlan(
        loop_id=loop.loop_id,
        feedback_artifact_ids=loop.feedback_artifact_ids,
        step_ids=loop.step_ids,
        terminal_step_id=loop.terminal_step_id,
        terminal_output_artifact_id=loop.terminal_output_artifact_id,
        fibers=(
            Fiber("propose", (Await(("outside",)), Invoke("propose"))),
            *loop.fibers[1:],
        ),
    )

    with pytest.raises(ExecutionPlanError, match="cycle requires explicit loop semantics"):
        await execute_plan(
            ExecutionPlan(plan.workflow_id, plan.fibers, (invalid_loop,)),
            graph,
            inputs={"state": 0},
            dispatch=_unexpected_dispatch,
        )


@pytest.mark.anyio
async def test_initial_loop_checkpoint_cannot_replace_workflow_input_seed() -> None:
    graph, plan = _counter_graph()
    checkpoint = create_execution_checkpoint(plan, graph, values={"state": 99})

    async def dispatch(
        step: StepNode,
        inputs: Mapping[str, object],
        context: DispatchContext,
    ) -> Mapping[str, object]:
        del step, inputs, context
        raise AssertionError("input mismatch must fail before dispatch")

    with pytest.raises(ExecutionPlanError, match="checkpoint input does not match current input"):
        await execute_plan(
            plan,
            graph,
            inputs={"state": 0},
            dispatch=dispatch,
            checkpoint=checkpoint,
        )


@pytest.mark.anyio
async def test_loop_checkpoint_completion_is_all_or_none() -> None:
    graph, plan = _counter_graph()
    checkpoint = create_execution_checkpoint(
        plan,
        graph,
        values={"state": 0},
        completed_step_ids=("propose",),
    )

    with pytest.raises(ExecutionPlanError, match="completion must be all-or-none"):
        await execute_plan(
            plan,
            graph,
            inputs={"state": 0},
            dispatch=_unexpected_dispatch,
            checkpoint=checkpoint,
        )


@pytest.mark.anyio
async def test_completed_loop_checkpoint_requires_committed_loop_state() -> None:
    graph, plan = _counter_graph()
    checkpoint = create_execution_checkpoint(
        plan,
        graph,
        values={"state": 1, "candidate": 1, "done": True},
        completed_step_ids=("advance", "propose", "terminal"),
    )

    with pytest.raises(ExecutionPlanError, match="has no committed loop state"):
        await execute_plan(
            plan,
            graph,
            inputs={"state": 0},
            dispatch=_unexpected_dispatch,
            checkpoint=checkpoint,
        )


@pytest.mark.anyio
async def test_loop_checkpoint_current_must_match_materialized_feedback() -> None:
    graph, plan = _counter_graph()
    checkpoint = create_execution_checkpoint(
        plan,
        graph,
        values={"state": 0},
        loops=(
            LoopExecutionCheckpoint(
                loop_id="terminal",
                epoch=1,
                current_values={"state": 1},
            ),
        ),
    )

    with pytest.raises(ExecutionPlanError, match="current value does not match materialized feedback"):
        await execute_plan(
            plan,
            graph,
            inputs={"state": 0},
            dispatch=_unexpected_dispatch,
            checkpoint=checkpoint,
        )


@pytest.mark.anyio
async def test_committed_loop_checkpoint_requires_completed_external_dependencies() -> None:
    graph, plan = _counter_graph()
    prep = _step("prep")
    config = ArtifactNode("config")
    graph = WorkflowGraph(
        workflow_id=graph.workflow_id,
        steps=(*graph.steps, prep),
        artifacts=(*graph.artifacts, config),
        edges=(
            *graph.edges,
            ProducesEdge("prep", "config"),
            ConsumesEdge("config", "propose"),
        ),
        policy=graph.policy,
    )
    loop = plan.loops[0]
    plan = ExecutionPlan(
        workflow_id=plan.workflow_id,
        fibers=(Fiber("prep", (Invoke("prep"),)), *plan.fibers),
        loops=(
            replace(
                loop,
                fibers=tuple(
                    replace(
                        fiber,
                        instructions=(Await(("prep",)), *fiber.instructions),
                    )
                    if fiber.fiber_id == "propose"
                    else fiber
                    for fiber in loop.fibers
                ),
            ),
        ),
    )
    checkpoint = create_execution_checkpoint(
        plan,
        graph,
        values={"state": 1},
        loops=(
            LoopExecutionCheckpoint(
                loop_id="terminal",
                epoch=1,
                current_values={"state": 1},
            ),
        ),
    )

    with pytest.raises(ExecutionPlanError, match=r"missing completed external dependencies.*prep"):
        await execute_plan(
            plan,
            graph,
            inputs={"state": 0},
            dispatch=_unexpected_dispatch,
            checkpoint=checkpoint,
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("saved", "message"),
    (
        (
            LoopExecutionCheckpoint(
                loop_id="terminal",
                epoch=0,
                current_values={"state": 0},
            ),
            "epoch must identify at least one committed barrier",
        ),
        (
            LoopExecutionCheckpoint(
                loop_id="terminal",
                epoch=1,
                current_values={"state": 0},
                staged_values={"candidate": 1},
            ),
            "must be an epoch barrier",
        ),
        (
            LoopExecutionCheckpoint(
                loop_id="terminal",
                epoch=1,
                current_values={"state": 0},
                completed_step_ids=("propose",),
            ),
            "must be an epoch barrier",
        ),
    ),
)
async def test_loop_checkpoint_must_describe_a_complete_epoch_barrier(
    saved: LoopExecutionCheckpoint,
    message: str,
) -> None:
    graph, plan = _counter_graph()
    checkpoint = create_execution_checkpoint(
        plan,
        graph,
        values={"state": 0},
        loops=(saved,),
    )

    with pytest.raises(ExecutionPlanError, match=message):
        await execute_plan(
            plan,
            graph,
            inputs={"state": 0},
            dispatch=_unexpected_dispatch,
            checkpoint=checkpoint,
        )


@pytest.mark.anyio
async def test_loop_checkpoint_rejects_forged_completed_top_step() -> None:
    graph, plan = _counter_graph()
    graph = WorkflowGraph(
        workflow_id=graph.workflow_id,
        steps=graph.steps,
        artifacts=graph.artifacts,
        edges=tuple(edge for edge in graph.edges if not (isinstance(edge, ConsumesEdge) and edge.step_id == "outside")),
        policy=graph.policy,
        selectors=graph.selectors,
    )
    checkpoint = create_execution_checkpoint(
        plan,
        graph,
        values={"state": 0, "observed": 0},
        completed_step_ids=("outside",),
    )

    with pytest.raises(ExecutionPlanError, match=r"not dependency-closed.*advance"):
        await execute_plan(
            plan,
            graph,
            inputs={"state": 0},
            dispatch=_unexpected_dispatch,
            checkpoint=checkpoint,
        )


@pytest.mark.anyio
async def test_loop_checkpoint_rejects_output_without_completed_producer() -> None:
    graph, plan = _counter_graph()
    checkpoint = create_execution_checkpoint(
        plan,
        graph,
        values={"state": 0, "observed": 0},
    )

    with pytest.raises(ExecutionPlanError, match="values must match materialized artifacts exactly"):
        await execute_plan(
            plan,
            graph,
            inputs={"state": 0},
            dispatch=_unexpected_dispatch,
            checkpoint=checkpoint,
        )


@pytest.mark.anyio
async def test_completed_loop_checkpoint_requires_true_terminal_result() -> None:
    graph, plan = _counter_graph()
    checkpoint = create_execution_checkpoint(
        plan,
        graph,
        values={"state": 1, "candidate": 1, "done": False},
        completed_step_ids=("advance", "propose", "terminal"),
        loops=(
            LoopExecutionCheckpoint(
                loop_id="terminal",
                epoch=1,
                current_values={"state": 1},
            ),
        ),
    )

    with pytest.raises(ExecutionPlanError, match="must materialize a true TerminalStep result"):
        await execute_plan(
            plan,
            graph,
            inputs={"state": 0},
            dispatch=_unexpected_dispatch,
            checkpoint=checkpoint,
        )


@pytest.mark.anyio
async def test_valid_completed_loop_checkpoint_resumes_external_consumer() -> None:
    graph, plan = _counter_graph()
    checkpoint = create_execution_checkpoint(
        plan,
        graph,
        values={"state": 1, "candidate": 1, "done": True},
        completed_step_ids=("advance", "propose", "terminal"),
        loops=(
            LoopExecutionCheckpoint(
                loop_id="terminal",
                epoch=1,
                current_values={"state": 1},
            ),
        ),
    )
    invoked: list[str] = []

    async def dispatch(
        step: StepNode,
        inputs: Mapping[str, object],
        context: DispatchContext,
    ) -> Mapping[str, object]:
        del context
        invoked.append(step.step_id)
        assert step.step_id == "outside"
        return {"observed": inputs["state"]}

    outputs = await execute_plan(
        plan,
        graph,
        inputs={"state": 0},
        dispatch=dispatch,
        checkpoint=checkpoint,
    )

    assert outputs == {"state": 1, "observed": 1}
    assert invoked == ["outside"]


@pytest.mark.anyio
async def test_loop_feedback_writers_read_one_immutable_snapshot() -> None:
    graph = WorkflowGraph(
        workflow_id="snapshot",
        steps=(_step("write_a"), _step("write_b"), _step("terminal", terminal=True)),
        artifacts=(
            ArtifactNode("a", is_input=True, is_output=True),
            ArtifactNode("b", is_input=True, is_output=True),
            ArtifactNode("done", artifact_type="BoolArtifact"),
        ),
        edges=(
            ConsumesEdge("a", "write_a"),
            ConsumesEdge("b", "write_a"),
            ProducesEdge("write_a", "a"),
            ConsumesEdge("a", "write_b"),
            ConsumesEdge("b", "write_b"),
            ProducesEdge("write_b", "b"),
            ConsumesEdge("a", "terminal"),
            ProducesEdge("terminal", "done"),
        ),
    )
    loop = LoopRegionPlan(
        loop_id="terminal",
        feedback_artifact_ids=("a", "b"),
        step_ids=("terminal", "write_a", "write_b"),
        terminal_step_id="terminal",
        terminal_output_artifact_id="done",
        fibers=tuple(Fiber(step_id, (Invoke(step_id),)) for step_id in ("write_a", "write_b", "terminal")),
    )

    async def dispatch(
        step: StepNode,
        inputs: Mapping[str, object],
        context: DispatchContext,
    ) -> Mapping[str, object]:
        del context
        if step.step_id == "write_a":
            return {"a": _int_value(inputs, "a") + _int_value(inputs, "b")}
        if step.step_id == "write_b":
            return {"b": _int_value(inputs, "a") - _int_value(inputs, "b")}
        return {"done": True}

    outputs = await execute_plan(
        ExecutionPlan("snapshot", (), (loop,)),
        graph,
        inputs={"a": 1, "b": 2},
        dispatch=dispatch,
    )

    assert outputs == {"a": 3, "b": -1}


@pytest.mark.anyio
async def test_terminal_requires_strict_bool_and_does_not_commit_partial_epoch() -> None:
    graph, plan = _counter_graph()
    checkpoints: list[ExecutionCheckpoint] = []
    outside_seen: list[object] = []

    async def dispatch(
        step: StepNode,
        inputs: Mapping[str, object],
        context: DispatchContext,
    ) -> Mapping[str, object]:
        del context
        if step.step_id == "propose":
            return {"candidate": _int_value(inputs, "state") + 1}
        if step.step_id == "advance":
            return {"state": inputs["candidate"]}
        if step.step_id == "terminal":
            return {"done": 1}
        outside_seen.append(inputs["state"])
        return {"observed": inputs["state"]}

    async def observe(checkpoint: ExecutionCheckpoint) -> None:
        checkpoints.append(checkpoint)

    with pytest.raises(ExceptionGroup) as raised:
        await execute_plan(
            plan,
            graph,
            inputs={"state": 0},
            dispatch=dispatch,
            checkpoint_observer=observe,
        )

    terminal_errors = raised.value.subgroup(lambda error: isinstance(error, StepOutputError))
    assert terminal_errors is not None
    assert "strict Boolean" in repr(terminal_errors)
    assert checkpoints == []
    assert outside_seen == []


@pytest.mark.anyio
async def test_loop_epoch_limit_is_a_backend_guard_and_checkpoints_barriers() -> None:
    graph, plan = _counter_graph()
    checkpoints: list[ExecutionCheckpoint] = []

    async def dispatch(
        step: StepNode,
        inputs: Mapping[str, object],
        context: DispatchContext,
    ) -> Mapping[str, object]:
        del context
        if step.step_id == "propose":
            return {"candidate": _int_value(inputs, "state") + 1}
        if step.step_id == "advance":
            return {"state": inputs["candidate"]}
        if step.step_id == "terminal":
            return {"done": False}
        raise AssertionError("outside consumer must not run before successful termination")

    async def observe(checkpoint: ExecutionCheckpoint) -> None:
        checkpoints.append(checkpoint)

    with pytest.raises(ExceptionGroup) as raised:
        await execute_plan(
            plan,
            graph,
            inputs={"state": 0},
            dispatch=dispatch,
            checkpoint_observer=observe,
            max_loop_epochs=2,
        )

    limit_errors = raised.value.subgroup(lambda error: isinstance(error, ExecutionPlanError))
    assert limit_errors is not None
    assert "max_loop_epochs=2" in repr(limit_errors)
    assert [checkpoint.loops[0].epoch for checkpoint in checkpoints] == [1, 2]
    assert [checkpoint.loops[0].current_values for checkpoint in checkpoints] == [
        {"state": 1},
        {"state": 2},
    ]
    assert all(not checkpoint.loops[0].staged_values for checkpoint in checkpoints)


def test_job_store_round_trips_loop_checkpoint_and_reads_legacy_checkpoint() -> None:
    checkpoint = ExecutionCheckpoint(
        workflow_id="counter",
        plan_digest="a" * 64,
        values={"state": 2},
        loops=(
            LoopExecutionCheckpoint(
                loop_id="terminal",
                epoch=2,
                current_values={"state": 2},
            ),
        ),
    )
    run = HumanWorkflowRun(
        run_id="0" * 32,
        status="running",
        flow_path="flows/counter.workflow",
        definition_digest="b" * 64,
        inputs={"state": 0},
        resource_capacities={},
        checkpoint=checkpoint,
    )

    encoded = _run_to_json(run)
    decoded = _run_from_json(encoded)
    assert decoded.checkpoint == checkpoint

    legacy = _run_to_json(run)
    legacy_checkpoint = cast(dict[str, object], legacy["checkpoint"])
    legacy_checkpoint.pop("loops")
    legacy_decoded = _run_from_json(legacy)
    assert legacy_decoded.checkpoint is not None
    assert legacy_decoded.checkpoint.loops == ()


@pytest.mark.anyio
async def test_artifact_store_can_publish_final_feedback_value_over_input_seed(tmp_path: Path) -> None:
    store = await ArtifactStore.open(
        anyio.Path(tmp_path),
        "0" * 32,
        reuse_existing=False,
    )
    await store.persist({"state": 0})
    await store.persist({"state": 1})
    assert await (store.artifacts_dir / "state.md").read_text() == "```json\n0\n```\n"

    await store.persist({"state": 3}, overwrite=True)

    assert await (store.artifacts_dir / "state.md").read_text() == "```json\n3\n```\n"
