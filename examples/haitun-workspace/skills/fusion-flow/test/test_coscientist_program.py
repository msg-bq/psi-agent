from __future__ import annotations

import io
import json
import runpy
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any, cast

import pytest
from fusion_flow.workflow_runner import compile_workflow

_WORKSPACE_DIR = Path(__file__).resolve().parents[3]
_WORKFLOW_DIR = _WORKSPACE_DIR / "flows" / "workflows" / "coscientist-ows"
_PROGRAM_PATH = _WORKSPACE_DIR / "skills" / "coscientist-ows-entry" / "scripts" / "program.py"
_DISTRIBUTED_SKILLS = (
    "coscientist-ows-entry",
    "mattergen-structure-sampler",
    "mattersim-structure-evaluator",
    "ows-catalyst-recommender",
    "round-parallel-synthesis-advisor",
    "source-liquid-sop-designer",
    "stage08-catalytic-performance-prover",
    "stage08-synthesis-safety-feasibility-judge",
)


@pytest.mark.parametrize(
    ("slug", "step_count"),
    [("single-step", 1), ("sequential", 2), ("parallel-join", 3)],
)
def test_short_workflow_compiles_with_current_executor_contract(
    slug: str,
    step_count: int,
) -> None:
    source = (_WORKSPACE_DIR / "flows" / "workflows" / slug / f"{slug}.workflow").read_text(encoding="utf-8")

    compiled = compile_workflow(source, strict_executors=True)

    assert len(compiled.graph.steps) == step_count
    assert set(compiled.executor_kinds.values()) == {"Agent"}


def _load_program() -> dict[str, Any]:
    assert _PROGRAM_PATH.is_file(), "coscientist Program executable is missing"
    return runpy.run_path(str(_PROGRAM_PATH))


def test_workflow_compiles_with_local_instruction_and_program_assets() -> None:
    source = (_WORKFLOW_DIR / "coscientist-ows.workflow").read_text(encoding="utf-8")

    compiled = compile_workflow(source, strict_executors=True)

    assert len(compiled.graph.steps) == 12
    assert set(compiled.executor_kinds.values()) == {"Agent", "Program"}
    assert not any(step.resources for step in compiled.graph.steps)
    for reference in (step.instruction_id for step in compiled.graph.steps):
        assert reference is not None
        assert reference.startswith("./")
        assert (_WORKFLOW_DIR / reference.removeprefix("./")).is_file()
    for reference in compiled.program_paths.values():
        assert reference.startswith("./")
        assert (_WORKSPACE_DIR / reference.removeprefix("./")).is_file()


def test_saved_workflow_has_public_distribution_assets() -> None:
    inputs_path = _WORKFLOW_DIR / "coscientist-ows.inputs.example.json"
    inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
    source = (_WORKFLOW_DIR / "coscientist-ows.workflow").read_text(encoding="utf-8")
    scheduler_source = (
        _WORKSPACE_DIR / "skills" / "coscientist-ows-entry" / "scripts" / "run_ows_streaming_scheduler.py"
    ).read_text(encoding="utf-8")
    compiled = compile_workflow(source, strict_executors=True)

    assert (_WORKFLOW_DIR / "README.md").is_file()
    assert "/public/home/" not in scheduler_source
    assert set(inputs) == {artifact.artifact_id for artifact in compiled.graph.artifacts if artifact.is_input}
    for skill_name in _DISTRIBUTED_SKILLS:
        assert (_WORKSPACE_DIR / "skills" / skill_name / "SKILL.md").is_file()


def test_performance_guidance_has_deterministic_program_guardrails() -> None:
    instruction = (_WORKFLOW_DIR / "instructions" / "prove-performance.md").read_text(encoding="utf-8")

    assert "program.py" in instruction
    assert "当前 Python 解释器" in instruction
    assert "slot_n/<folder>" in instruction
    assert "不得覆盖已有结果" in instruction
    assert "UTF-8 无 BOM" in instruction
    assert "不得安装依赖" in instruction
    assert "不得读取或回显 `LLM_PROOF_API_KEY`" in instruction
    for path in (
        _WORKSPACE_DIR / "skills" / "stage08-catalytic-performance-prover" / "SKILL.md",
        _WORKSPACE_DIR / "skills" / "stage08-catalytic-performance-prover" / "LLM_proof" / "README.md",
    ):
        guidance = path.read_text(encoding="utf-8")
        assert "PowerShell" in guidance
        assert r".venv\Scripts\python.exe" in guidance
        assert "Do not install dependencies" in guidance
        assert "Do not read, print, or log `LLM_PROOF_API_KEY`" in guidance


def test_program_main_dispatches_from_materialized_instruction_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    namespace = _load_program()
    main = namespace["main"]
    calls: list[str] = []

    def prepare(inputs: dict[str, object], workspace: Path) -> dict[str, object]:
        del inputs, workspace
        calls.append("prepare")
        return {"handler": "prepare"}

    def merge(inputs: dict[str, object], workspace: Path) -> dict[str, object]:
        del inputs, workspace
        calls.append("merge")
        return {"handler": "merge"}

    def performance(inputs: dict[str, object], workspace: Path) -> dict[str, object]:
        del inputs, workspace
        calls.append("performance")
        return {"handler": "performance"}

    main.__globals__["prepare"] = prepare
    main.__globals__["merge"] = merge
    main.__globals__["performance"] = performance
    cases = (
        ({"result_directory_name": "results"}, "prepare"),
        ({"tmp_candidates_directory_initial": "results/tmp/candidates"}, "merge"),
        (
            {
                "tmp_candidates_directory_after_recommendations": ("results/tmp/candidates"),
            },
            "performance",
        ),
    )
    for inputs, expected in cases:
        stdout = io.StringIO()
        monkeypatch.setattr(
            sys,
            "stdin",
            io.StringIO(
                json.dumps(
                    {
                        "instruction": "Materialized instruction text.",
                        "inputs": inputs,
                    }
                )
            ),
        )
        monkeypatch.setattr(sys, "stdout", stdout)

        assert main() == 0
        assert json.loads(stdout.getvalue()) == {"handler": expected}

    assert calls == ["prepare", "merge", "performance"]


def test_prepare_program_initializes_all_declared_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connections: list[sqlite3.Connection] = []
    original_connect = sqlite3.connect

    class TrackingConnection(sqlite3.Connection):
        closed = False

        def close(self) -> None:
            self.closed = True
            super().close()

    def connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        kwargs["factory"] = TrackingConnection
        connection = original_connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", connect)
    scheduler_source = _WORKSPACE_DIR / "skills" / "coscientist-ows-entry"
    shutil.copytree(
        scheduler_source,
        tmp_path / "skills" / "coscientist-ows-entry",
    )
    prepare = _load_program()["prepare"]

    outputs = prepare(
        {
            "candidate_knowledge_base_initial": {"candidates": []},
            "result_directory_name": "results",
        },
        tmp_path,
    )

    assert set(outputs) == {
        "candidate_catalyst_pool_initial",
        "candidate_catalyst_structure_pool_initial",
        "candidate_knowledge_base",
        "fail_candidates_directory_initial",
        "fail_directory",
        "mattergen_stage_directory_initial",
        "mattersim_stage_directory_initial",
        "novel_and_stable_catalysts_initial",
        "prepare_workflow_step_result",
        "recommender_slot_1_directory",
        "recommender_slot_2_directory",
        "recommender_slot_3_directory",
        "recommender_slot_4_directory",
        "round_parallel_synthesis_stage_directory_initial",
        "scheduler_state",
        "tmp_candidates_directory_initial",
        "tmp_knowledge_directory_initial",
        "workflow_run_context",
    }
    assert outputs["candidate_knowledge_base"] == {"candidates": []}
    assert (tmp_path / outputs["scheduler_state"]).is_file()
    assert (tmp_path / outputs["prepare_workflow_step_result"]).is_file()
    assert connections
    assert all(cast(TrackingConnection, connection).closed for connection in connections)


def test_merge_program_preserves_each_slot_directory(tmp_path: Path) -> None:
    merge = _load_program()["merge"]
    candidate_destination = tmp_path / "results" / "tmp" / "candidates"
    knowledge_destination = tmp_path / "results" / "tmp" / "knowledge"
    candidate_destination.mkdir(parents=True)
    knowledge_destination.mkdir(parents=True)
    inputs: dict[str, object] = {
        "tmp_candidates_directory_initial": str(candidate_destination),
        "tmp_knowledge_directory_initial": str(knowledge_destination),
    }
    for slot in range(1, 5):
        candidate_source = tmp_path / "candidate-deltas" / f"slot_{slot}"
        knowledge_source = tmp_path / "knowledge-deltas" / f"slot_{slot}"
        candidate_source.mkdir(parents=True)
        knowledge_source.mkdir(parents=True)
        (candidate_source / "candidate.json").write_text("{}", encoding="utf-8")
        (knowledge_source / "manifest.json").write_text(
            '{"captured": false}',
            encoding="utf-8",
        )
        inputs[f"tmp_candidates_directory_from_recommend_{slot}"] = str(candidate_source)
        inputs[f"tmp_knowledge_directory_from_recommend_{slot}"] = str(knowledge_source)

    outputs = merge(inputs, tmp_path)

    assert outputs == {
        "tmp_candidates_directory_after_recommendations": "results/tmp/candidates",
        "tmp_knowledge_directory": "results/tmp/knowledge",
    }
    for slot in range(1, 5):
        assert (candidate_destination / f"slot_{slot}" / "candidate.json").is_file()
        assert (knowledge_destination / f"slot_{slot}" / "manifest.json").is_file()


def test_merge_program_rejects_conflicting_slot_directory(tmp_path: Path) -> None:
    merge = _load_program()["merge"]
    candidate_destination = tmp_path / "results" / "tmp" / "candidates"
    knowledge_destination = tmp_path / "results" / "tmp" / "knowledge"
    (candidate_destination / "slot_1").mkdir(parents=True)
    knowledge_destination.mkdir(parents=True)
    candidate_source = tmp_path / "candidate-deltas" / "slot_1"
    knowledge_source = tmp_path / "knowledge-deltas" / "slot_1"
    candidate_source.mkdir(parents=True)
    knowledge_source.mkdir(parents=True)
    inputs: dict[str, object] = {
        "tmp_candidates_directory_initial": str(candidate_destination),
        "tmp_knowledge_directory_initial": str(knowledge_destination),
    }
    for slot in range(1, 5):
        inputs[f"tmp_candidates_directory_from_recommend_{slot}"] = str(candidate_source)
        inputs[f"tmp_knowledge_directory_from_recommend_{slot}"] = str(knowledge_source)

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        merge(inputs, tmp_path)


def _write_candidate(
    workspace: Path,
    relative_path: str,
    *,
    candidate_id: str,
    name: str,
    formula: str,
) -> Path:
    candidate = workspace / "results" / "tmp" / "candidates" / relative_path
    candidate.mkdir(parents=True)
    (candidate / "CANDIDATE_PAYLOAD.json").write_text(
        json.dumps(
            {
                "candidate_id": candidate_id,
                "candidate_name": name,
                "main_photocatalyst": formula,
            }
        ),
        encoding="utf-8",
    )
    return candidate


def test_performance_program_proves_and_moves_by_directory_identity(
    tmp_path: Path,
) -> None:
    performance = _load_program()["performance"]
    retained = _write_candidate(
        tmp_path,
        "slot_1/actual-retained-folder",
        candidate_id="duplicate-id",
        name="Retained catalyst",
        formula="RetainedFormula",
    )
    rejected = _write_candidate(
        tmp_path,
        "slot_2/actual-rejected-folder",
        candidate_id="duplicate-id",
        name="Rejected catalyst",
        formula="RejectedFormula",
    )
    proof_inputs: list[dict[str, object]] = []

    def run_proof(input_json: Path, output: Path, audit: Path) -> None:
        payload = json.loads(input_json.read_text(encoding="utf-8"))
        proof_inputs.append(payload)
        record = payload["retained_records"][0]
        rejected_candidate = record["catalyst_name"] == "Rejected catalyst"
        output.write_text(
            f"# Proof\n\n### 1. {record['catalyst_name']}\n\nEvidence.\n",
            encoding="utf-8",
        )
        audit.write_text(
            json.dumps(
                {
                    "total": 1,
                    "no_catalytic_performance": {
                        "no_catalytic_performance_count": (1 if rejected_candidate else 0),
                        "no_catalytic_performance_indices": ([1] if rejected_candidate else []),
                    },
                }
            ),
            encoding="utf-8",
        )

    outputs = performance(
        {
            "tmp_candidates_directory_after_recommendations": ("results/tmp/candidates"),
            "candidate_catalyst_pool_initial": "results/pools/candidates",
            "fail_candidates_directory_initial": "results/fail/candidates",
        },
        tmp_path,
        run_proof=run_proof,
    )

    retained_target = tmp_path / "results" / "pools" / "candidates" / "slot_1" / "actual-retained-folder"
    rejected_target = tmp_path / "results" / "fail" / "candidates" / "slot_2" / "actual-rejected-folder"
    assert not retained.exists()
    assert not rejected.exists()
    for target in (retained_target, rejected_target):
        assert (target / "CATALYTIC_PERFORMANCE_PROOF.md").is_file()
        assert (target / "CATALYTIC_PERFORMANCE_PROOF.md.audit.json").is_file()
    assert proof_inputs == [
        {
            "retained_records": [
                {
                    "catalyst_name": "Retained catalyst",
                    "recommended_formula": "RetainedFormula",
                }
            ]
        },
        {
            "retained_records": [
                {
                    "catalyst_name": "Rejected catalyst",
                    "recommended_formula": "RejectedFormula",
                }
            ]
        },
    ]
    assert outputs == {
        "candidate_catalyst_pool_after_performance_proof": ("results/pools/candidates"),
        "fail_candidates_directory_after_performance_proof": ("results/fail/candidates"),
        "performance_proven_catalysts": ["results/pools/candidates/slot_1/actual-retained-folder"],
        "performance_rejected_catalysts": ["results/fail/candidates/slot_2/actual-rejected-folder"],
        "tmp_candidates_directory": "results/tmp/candidates",
    }


def test_performance_program_refuses_existing_destination_before_api_call(
    tmp_path: Path,
) -> None:
    performance = _load_program()["performance"]
    _write_candidate(
        tmp_path,
        "slot_1/candidate",
        candidate_id="candidate",
        name="Candidate",
        formula="Formula",
    )
    (tmp_path / "results" / "pools" / "candidates" / "slot_1" / "candidate").mkdir(parents=True)
    calls = 0

    def run_proof(input_json: Path, output: Path, audit: Path) -> None:
        del input_json, output, audit
        nonlocal calls
        calls += 1

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        performance(
            {
                "tmp_candidates_directory_after_recommendations": ("results/tmp/candidates"),
                "candidate_catalyst_pool_initial": "results/pools/candidates",
                "fail_candidates_directory_initial": "results/fail/candidates",
            },
            tmp_path,
            run_proof=run_proof,
        )

    assert calls == 0
