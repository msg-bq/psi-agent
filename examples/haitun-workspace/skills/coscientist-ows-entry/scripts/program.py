#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import cast


def _workspace_path(workspace: Path, value: object, *, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty path string")
    candidate = Path(value)
    resolved = (candidate if candidate.is_absolute() else workspace / candidate).resolve()
    workspace = workspace.resolve()
    if not resolved.is_relative_to(workspace) or resolved == workspace:
        raise ValueError(f"{label} must stay below the workspace root")
    return resolved


def _relative(workspace: Path, path: Path) -> str:
    return path.resolve().relative_to(workspace.resolve()).as_posix()


def prepare(inputs: dict[str, object], workspace: Path) -> dict[str, object]:
    output_root = _workspace_path(
        workspace,
        inputs.get("result_directory_name"),
        label="result_directory_name",
    )
    scheduler_path = workspace / "skills" / "coscientist-ows-entry" / "scripts" / "run_ows_streaming_scheduler.py"
    namespace: dict[str, object] = {
        "__file__": str(scheduler_path),
        "__name__": "coscientist_ows_scheduler",
    }
    exec(
        compile(scheduler_path.read_text(encoding="utf-8"), str(scheduler_path), "exec"),
        namespace,
    )
    command_init = namespace.get("command_init")
    if not callable(command_init):
        raise RuntimeError(f"scheduler has no command_init: {scheduler_path}")
    command_init = cast(Callable[[SimpleNamespace], dict[str, object]], command_init)
    entry_dir = output_root / "00-coscientist-ows-entry"
    scheduler_result = command_init(
        SimpleNamespace(
            repo_root=str(workspace),
            output_root=str(output_root),
            knowledge_base_path="data/knowledge-base/knowledge_base_for_agent.json",
            recommendation_branch="single-photocatalyst",
            execution_scope="full",
            gpu_id="",
            target_recommendation_count=None,
            recommendation_parallelism=4,
            mattersim_batch_size=8,
            resume=(entry_dir / "PARAMETERS.json").exists(),
        )
    )

    paths = {
        "mattergen_stage_directory_initial": output_root / "04-mattergen-structure-sampler",
        "mattersim_stage_directory_initial": output_root / "05-mattersim-structure-evaluator",
        "round_parallel_synthesis_stage_directory_initial": (output_root / "08-round-parallel-synthesis-advisor"),
        "candidate_catalyst_pool_initial": output_root / "pools" / "candidates",
        "candidate_catalyst_structure_pool_initial": output_root / "pools" / "structures",
        "novel_and_stable_catalysts_initial": (output_root / "pools" / "novel_and_stable_catalysts"),
        "fail_directory": output_root / "fail",
        "fail_candidates_directory_initial": output_root / "fail" / "candidates",
        "tmp_candidates_directory_initial": output_root / "tmp" / "candidates",
        "tmp_knowledge_directory_initial": output_root / "tmp" / "knowledge",
        **{
            f"recommender_slot_{slot}_directory": (output_root / "02-ows-catalyst-recommender" / f"slot_{slot}")
            for slot in range(1, 5)
        },
    }
    for path in (
        *paths.values(),
        output_root / "05-mattersim-structure-evaluator" / "streaming" / "batches",
        output_root / "08-round-parallel-synthesis-advisor" / "rounds",
        output_root / "08-round-parallel-synthesis-advisor" / "synthesis-routes",
        output_root / "pools" / "knowledge",
    ):
        path.mkdir(parents=True, exist_ok=True)

    prepare_result = entry_dir / "PREPARE_WORKFLOW_STEP_RESULT.json"
    outputs: dict[str, object] = {
        "workflow_run_context": {
            "output_root": _relative(workspace, output_root),
            "scheduler": scheduler_result,
        },
        "scheduler_state": _relative(
            workspace,
            entry_dir / "STREAMING_SCHEDULER_STATE.json",
        ),
        **{key: _relative(workspace, path) for key, path in paths.items()},
        "candidate_knowledge_base": inputs.get("candidate_knowledge_base_initial"),
        "prepare_workflow_step_result": _relative(workspace, prepare_result),
    }
    prepare_result.write_text(
        json.dumps(outputs, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return outputs


def _merge_directories(destination: Path, sources: list[Path]) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for source in sources:
        if not source.is_dir():
            raise FileNotFoundError(f"recommendation delta directory does not exist: {source}")
        if source.is_relative_to(destination):
            continue
        target = destination / source.name
        if target.exists():
            raise FileExistsError(f"refusing to overwrite recommendation delta: {target}")
        shutil.copytree(source, target)


def merge(inputs: dict[str, object], workspace: Path) -> dict[str, object]:
    candidate_destination = _workspace_path(
        workspace,
        inputs.get("tmp_candidates_directory_initial"),
        label="tmp_candidates_directory_initial",
    )
    knowledge_destination = _workspace_path(
        workspace,
        inputs.get("tmp_knowledge_directory_initial"),
        label="tmp_knowledge_directory_initial",
    )
    candidate_sources = [
        _workspace_path(
            workspace,
            inputs.get(f"tmp_candidates_directory_from_recommend_{slot}"),
            label=f"tmp_candidates_directory_from_recommend_{slot}",
        )
        for slot in range(1, 5)
    ]
    knowledge_sources = [
        _workspace_path(
            workspace,
            inputs.get(f"tmp_knowledge_directory_from_recommend_{slot}"),
            label=f"tmp_knowledge_directory_from_recommend_{slot}",
        )
        for slot in range(1, 5)
    ]
    _merge_directories(candidate_destination, candidate_sources)
    _merge_directories(knowledge_destination, knowledge_sources)
    return {
        "tmp_candidates_directory_after_recommendations": _relative(
            workspace,
            candidate_destination,
        ),
        "tmp_knowledge_directory": _relative(workspace, knowledge_destination),
    }


def _run_proof(input_json: Path, output: Path, audit: Path) -> None:
    runner = (
        Path(__file__).resolve().parents[3]
        / "skills"
        / "stage08-catalytic-performance-prover"
        / "LLM_proof"
        / "run_llm_proof.py"
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(runner),
            "--input-json",
            str(input_json),
            "--output",
            str(output),
            "--audit-json",
            str(audit),
            "--concurrency",
            "1",
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(
            f"catalytic performance proof failed with exit code {completed.returncode}: {detail[-4000:]}"
        )


def performance(
    inputs: dict[str, object],
    workspace: Path,
    *,
    run_proof: Callable[[Path, Path, Path], None] = _run_proof,
) -> dict[str, object]:
    pending_root = _workspace_path(
        workspace,
        inputs.get("tmp_candidates_directory_after_recommendations"),
        label="tmp_candidates_directory_after_recommendations",
    )
    pool_root = _workspace_path(
        workspace,
        inputs.get("candidate_catalyst_pool_initial"),
        label="candidate_catalyst_pool_initial",
    )
    fail_root = _workspace_path(
        workspace,
        inputs.get("fail_candidates_directory_initial"),
        label="fail_candidates_directory_initial",
    )
    if not pending_root.is_dir():
        raise FileNotFoundError(f"candidate directory does not exist: {pending_root}")
    pool_root.mkdir(parents=True, exist_ok=True)
    fail_root.mkdir(parents=True, exist_ok=True)

    candidates: list[tuple[Path, Path, str, str]] = []
    for payload_path in sorted(pending_root.glob("slot_*/*/CANDIDATE_PAYLOAD.json")):
        candidate = payload_path.parent
        relative = candidate.relative_to(pending_root)
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"candidate payload must be an object: {payload_path}")
        name = payload.get("candidate_name")
        formula = payload.get("main_photocatalyst")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"candidate_name must be non-empty: {payload_path}")
        if not isinstance(formula, str) or not formula.strip():
            raise ValueError(f"main_photocatalyst must be non-empty: {payload_path}")
        for root in (pool_root, fail_root):
            target = root / relative
            if target.exists():
                raise FileExistsError(f"refusing to overwrite candidate: {target}")
        candidates.append((candidate, relative, name.strip(), formula.strip()))

    movements: list[tuple[Path, Path, bool]] = []
    with tempfile.TemporaryDirectory(prefix=".coscientist-stage08-", dir=workspace) as temporary:
        temporary_root = Path(temporary)
        for index, (candidate, relative, name, formula) in enumerate(
            candidates,
            start=1,
        ):
            input_json = temporary_root / f"candidate-{index}.json"
            input_json.write_text(
                json.dumps(
                    {
                        "retained_records": [
                            {
                                "catalyst_name": name,
                                "recommended_formula": formula,
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            proof = candidate / "CATALYTIC_PERFORMANCE_PROOF.md"
            audit = candidate / "CATALYTIC_PERFORMANCE_PROOF.md.audit.json"
            run_proof(input_json, proof, audit)
            proof_text = proof.read_text(encoding="utf-8")
            audit_payload = json.loads(audit.read_text(encoding="utf-8"))
            if proof_text.count("\n### ") != 1 or not isinstance(audit_payload, dict):
                raise ValueError(f"invalid proof output for candidate: {candidate}")
            judgement = audit_payload.get("no_catalytic_performance")
            total = audit_payload.get("total")
            if not isinstance(judgement, dict) or total != 1:
                raise ValueError(f"invalid proof audit for candidate: {candidate}")
            count = judgement.get("no_catalytic_performance_count")
            indices = judgement.get("no_catalytic_performance_indices")
            if (count, indices) not in ((0, []), (1, [1])):
                raise ValueError(f"invalid proof judgement for candidate: {candidate}")
            rejected = count == 1
            movements.append((candidate, (fail_root if rejected else pool_root) / relative, rejected))

    proven: list[str] = []
    rejected: list[str] = []
    for source, target, is_rejected in movements:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        (rejected if is_rejected else proven).append(_relative(workspace, target))
    return {
        "tmp_candidates_directory": _relative(workspace, pending_root),
        "candidate_catalyst_pool_after_performance_proof": _relative(
            workspace,
            pool_root,
        ),
        "fail_candidates_directory_after_performance_proof": _relative(
            workspace,
            fail_root,
        ),
        "performance_proven_catalysts": proven,
        "performance_rejected_catalysts": rejected,
    }


def main() -> int:
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise ValueError("Program stdin must be a JSON object")
    inputs = payload.get("inputs")
    instruction = payload.get("instruction")
    if not isinstance(inputs, dict) or not all(isinstance(key, str) for key in inputs):
        raise ValueError("Program inputs must be a JSON object with string keys")
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError("Program instruction must be non-empty text")
    workspace = Path(__file__).resolve().parents[3]
    operations = [
        handler
        for sentinel, handler in (
            ("result_directory_name", prepare),
            ("tmp_candidates_directory_initial", merge),
            ("tmp_candidates_directory_after_recommendations", performance),
        )
        if sentinel in inputs
    ]
    if len(operations) != 1:
        raise ValueError("Program inputs do not identify exactly one supported operation")
    outputs = operations[0](cast(dict[str, object], inputs), workspace)
    json.dump(outputs, sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
