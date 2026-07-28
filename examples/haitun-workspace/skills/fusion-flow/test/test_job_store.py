from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import Any

import anyio
import pytest
from fusion_flow_next.job_store import (
    HumanRequestSpec,
    HumanWorkflowRun,
    InvalidRunStateError,
    JobStore,
    JobStoreError,
    RunAlreadyActiveError,
)

from psi_agent.workflow_execution import ExecutionCheckpoint


@pytest.mark.anyio
async def test_job_store_round_trips_waiting_human_state(tmp_path: Any) -> None:
    store = JobStore(tmp_path / "runs")
    run = await store.create(
        flow_path="flows/review.workflow",
        flow_source="const review: Workflow;",
        inputs={"proposal": {"version": 2}},
        resource_capacities={"gpu": ("gpu-a", "gpu-b"), "browser": 1},
    )

    assert re.fullmatch(r"[0-9a-f]{32}", run.run_id)
    assert run.status == "running"
    checkpoint = ExecutionCheckpoint(
        values={"proposal": {"version": 2}, "draft": "ready"},
        completed_step_ids=("draft_step",),
    )
    request = HumanRequestSpec.create(
        step_id="review_step",
        question="Approve the proposal or provide edits?",
        output_artifact_ids=("review",),
        options=("Approve", "Request changes"),
        recommended=1,
    )
    waiting = replace(
        run,
        status="waiting_for_human",
        checkpoint=checkpoint,
        prepared_request=request,
    )

    async with store.acquire(run.run_id) as lease:
        await lease.save(waiting)

    loaded = await store.load(run.run_id)
    assert loaded == waiting
    assert loaded.resource_capacities == {
        "browser": 1,
        "gpu": ("gpu-a", "gpu-b"),
    }

    state_path = anyio.Path(tmp_path / "runs" / f"{run.run_id}.json")
    payload = json.loads(await state_path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert payload["prepared_request"]["request_id"] == request.request_id
    assert payload["checkpoint"] == {
        "values": {"draft": "ready", "proposal": {"version": 2}},
        "completed_step_ids": ["draft_step"],
        "completed_selection_ids": [],
    }


@pytest.mark.anyio
async def test_job_store_persists_response_and_completed_outputs(tmp_path: Any) -> None:
    store = JobStore(tmp_path)
    run = await store.create(
        flow_path="review.workflow",
        flow_source="workflow",
        inputs={"request": "review"},
        checkpoint=ExecutionCheckpoint(values={"request": "review"}),
    )
    request = HumanRequestSpec.create(
        step_id="review",
        question="What should change?",
        output_artifact_ids=("feedback",),
    )
    waiting = replace(
        run,
        status="waiting_for_human",
        prepared_request=request,
    )
    async with store.acquire(run.run_id) as lease:
        await lease.save(waiting)
        resumed = replace(
            waiting,
            status="running",
            prepared_request=None,
            human_responses={request.request_id: "Tighten the conclusion."},
        )
        await lease.save(resumed)
        completed = replace(
            resumed,
            status="completed",
            outputs={"result": {"accepted": True}},
        )
        await lease.save(completed)

    loaded = await store.load(run.run_id)
    assert loaded.status == "completed"
    assert loaded.human_responses == {request.request_id: "Tighten the conclusion."}
    assert loaded.outputs == {"result": {"accepted": True}}


@pytest.mark.anyio
async def test_acquire_rejects_duplicate_active_run_and_releases_after_error(
    tmp_path: Any,
) -> None:
    store = JobStore(tmp_path)
    run = await store.create(
        flow_path="flow.workflow",
        flow_source="workflow",
        inputs={},
    )

    with pytest.raises(RuntimeError, match="stop"):
        async with store.acquire(run.run_id) as lease:
            assert await lease.load() == run
            with pytest.raises(RunAlreadyActiveError, match="already active"):
                async with store.acquire(run.run_id):
                    pytest.fail("duplicate lease was granted")
            raise RuntimeError("stop")

    async with store.acquire(run.run_id) as lease:
        assert await lease.load() == run

    with pytest.raises(JobStoreError, match="no longer active"):
        await lease.load()


@pytest.mark.anyio
async def test_load_strictly_rejects_unknown_fields_and_filename_mismatch(
    tmp_path: Any,
) -> None:
    store = JobStore(tmp_path)
    run = await store.create(
        flow_path="flow.workflow",
        flow_source="workflow",
        inputs={},
    )
    state_path = anyio.Path(tmp_path / f"{run.run_id}.json")
    payload = json.loads(await state_path.read_text(encoding="utf-8"))
    payload["unexpected"] = True
    await state_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(InvalidRunStateError, match="unknown=\\['unexpected'\\]"):
        await store.load(run.run_id)


@pytest.mark.anyio
async def test_load_rejects_path_traversal_identifier(tmp_path: Any) -> None:
    store = JobStore(tmp_path)

    with pytest.raises(ValueError, match="32 lowercase hexadecimal"):
        await store.load("../outside")


def test_run_state_rejects_non_json_values_and_invalid_clarify_spec() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        HumanWorkflowRun(
            run_id="a" * 32,
            status="running",
            flow_path="flow.workflow",
            flow_source_digest="b" * 64,
            inputs={"bad": float("nan")},
            resource_capacities={},
        )

    with pytest.raises(ValueError, match="at most four"):
        HumanRequestSpec.create(
            step_id="review",
            question="Choose",
            output_artifact_ids=("answer",),
            options=("1", "2", "3", "4", "5"),
        )
