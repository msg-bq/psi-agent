from __future__ import annotations

import importlib.util
import os
import re
import sys
from collections import Counter
from typing import Any, cast

import pytest

from psi_agent.workflow_execution import ExecutionPlanError, generate_plan
from psi_agent.workflow_graph.model import ConsumesEdge, ProducesEdge

_EXAMPLE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "examples",
    "catalyst",
)
_WORKFLOW_PATH = os.path.join(_EXAMPLE_DIR, "catalyst.workflow")

_SKILL_DIR = os.path.dirname(os.path.dirname(__file__))
_PACKAGE_DIR = os.path.join(_SKILL_DIR, "fusion_flow_next")
_RUNNER_PATH = os.path.join(_SKILL_DIR, "examples", "run_workflow.py")


def _load_module(name: str, path: str, package_paths: list[str] | None = None) -> Any:
    spec = importlib.util.spec_from_file_location(name, path, submodule_search_locations=package_paths)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return cast(Any, module)


fusion_flow_next = _load_module(
    "fusion_flow_next",
    os.path.join(_PACKAGE_DIR, "__init__.py"),
    [_PACKAGE_DIR],
)
parse_workflow = fusion_flow_next.parse_workflow
ParseContext = fusion_flow_next.ParseContext
Concept = fusion_flow_next.Concept
Operator = fusion_flow_next.Operator
Constant = fusion_flow_next.Constant
CompoundTerm = fusion_flow_next.CompoundTerm
WorkflowFile = fusion_flow_next.WorkflowFile
WorkflowGraphCompiler = fusion_flow_next.WorkflowGraphCompiler
run_workflow = _load_module("fusion_flow_next_catalyst_runner", _RUNNER_PATH)


def _parse_context(source: str) -> ParseContext:
    concept_names = {
        declared for _, declared in re.findall(r"(?m)^const\s+([A-Za-z_]\w*)\s*:\s*([A-Za-z_]\w*)\s*;", source)
    }
    concept_names |= {"Bool", "ComplexNumber", "Step", "Instruction"}
    concepts = {name: Concept(name=name) for name in concept_names | {"Bool", "ComplexNumber"}}
    operator_names = set(re.findall(r"(?m)^\s*([A-Za-z_]\w*)\s*\(", source))
    operators = {name: Operator(name=name) for name in operator_names}
    operators["step_instruction"] = Operator(
        name="step_instruction",
        input_concepts=(concepts["Step"],),
        output_concept=concepts["Instruction"],
    )
    return ParseContext(concepts=concepts, operators=operators)


def test_catalyst_runner_reaches_catalog_assertion_boundary() -> None:
    with open(_WORKFLOW_PATH, encoding="utf-8") as workflow_file:
        source = workflow_file.read()

    with pytest.raises(ValueError, match="workflow contains assertions that the graph compiler cannot execute"):
        run_workflow.compile_workflow(source)


def test_catalyst_example_migrates_instructions_and_preserves_backend_boundary() -> None:
    with open(_WORKFLOW_PATH, encoding="utf-8") as workflow_file:
        source = workflow_file.read()
    result = parse_workflow(source, context=_parse_context(source))

    assert result.diagnostics == ()
    assert isinstance(result.core_ir, WorkflowFile)
    instruction_relations = [
        assertion
        for assertion in result.core_ir.workflows[0].assertions
        if isinstance(assertion.lhs, CompoundTerm) and assertion.lhs.operator.name == "step_instruction"
    ]
    instruction_paths = [
        assertion.rhs.symbol for assertion in instruction_relations if isinstance(assertion.rhs, Constant)
    ]

    assert len(instruction_paths) == len(instruction_relations) == 12
    assert set(instruction_paths) == {
        "./instructions/analyze-route-feasibility.md",
        "./instructions/design-synthesis-route.md",
        "./instructions/evaluate-structures.md",
        "./instructions/merge-recommendation-outputs.md",
        "./instructions/prepare-workflow.md",
        "./instructions/prove-performance.md",
        "./instructions/recommend-candidate.md",
        "./instructions/sample-structure.md",
        "./instructions/shutdown-workflow.md",
    }
    assert all(path.startswith("./instructions/") for path in instruction_paths)
    assert instruction_paths.count("./instructions/recommend-candidate.md") == 4
    recommendation_steps = {
        assertion.lhs.arguments[0].symbol
        for assertion in instruction_relations
        if isinstance(assertion.lhs.arguments[0], Constant)
        and isinstance(assertion.rhs, Constant)
        and assertion.rhs.symbol == "./instructions/recommend-candidate.md"
    }
    assert recommendation_steps == {
        "recommend_1_step",
        "recommend_2_step",
        "recommend_3_step",
        "recommend_4_step",
    }
    for instruction_path in instruction_paths:
        with open(
            os.path.join(_EXAMPLE_DIR, instruction_path.removeprefix("./")),
            encoding="utf-8",
        ) as instruction_file:
            assert instruction_file.read().strip()
    with open(
        os.path.join(_EXAMPLE_DIR, "instructions", "recommend-candidate.md"),
        encoding="utf-8",
    ) as recommendation_instruction_file:
        assert "captured=false" in recommendation_instruction_file.read()

    compiled = WorkflowGraphCompiler().compile(result.core_ir)
    assert isinstance(compiled, tuple)
    (compilation,) = compiled

    input_artifacts = {artifact.artifact_id for artifact in compilation.graph.artifacts if artifact.is_input}
    produced_artifacts = {edge.artifact_id for edge in compilation.graph.edges if isinstance(edge, ProducesEdge)}
    assert input_artifacts.isdisjoint(produced_artifacts)

    expected_final_producers = {
        "tmp_candidates_directory": "performance_proof_step",
        "tmp_knowledge_directory": "merge_recommendation_outputs_step",
        "candidate_catalyst_pool": "mattergen_step",
        "candidate_catalyst_structure_pool": "mattersim_step",
        "fail_candidates_directory": "synthesis_route_design_step",
        "novel_and_stable_catalysts": "synthesis_route_design_step",
        "mattergen_stage_directory": "mattergen_step",
        "mattersim_stage_directory": "mattersim_step",
        "round_parallel_synthesis_stage_directory": "synthesis_route_design_step",
    }
    producer_by_artifact = {
        edge.artifact_id: edge.step_id
        for edge in compilation.graph.edges
        if isinstance(edge, ProducesEdge) and edge.artifact_id in expected_final_producers
    }
    assert producer_by_artifact == expected_final_producers

    merge_consumes = {
        edge.artifact_id
        for edge in compilation.graph.edges
        if isinstance(edge, ConsumesEdge) and edge.step_id == "merge_recommendation_outputs_step"
    }
    assert merge_consumes == {
        "tmp_candidates_directory_initial",
        "tmp_knowledge_directory_initial",
        "tmp_candidates_directory_from_recommend_1",
        "tmp_candidates_directory_from_recommend_2",
        "tmp_candidates_directory_from_recommend_3",
        "tmp_candidates_directory_from_recommend_4",
        "tmp_knowledge_directory_from_recommend_1",
        "tmp_knowledge_directory_from_recommend_2",
        "tmp_knowledge_directory_from_recommend_3",
        "tmp_knowledge_directory_from_recommend_4",
    }
    merge_produces = {
        edge.artifact_id
        for edge in compilation.graph.edges
        if isinstance(edge, ProducesEdge) and edge.step_id == "merge_recommendation_outputs_step"
    }
    assert merge_produces == {
        "tmp_candidates_directory_after_recommendations",
        "tmp_knowledge_directory",
    }
    residual_operator_counts = Counter(
        assertion.lhs.operator.name
        for assertion in compilation.residual_assertions
        if isinstance(assertion.lhs, CompoundTerm)
    )
    assert residual_operator_counts == Counter(
        {
            "allowed_tool": 11,
            "batch_size": 1,
            "exclusive_lease": 2,
            "independent": 4,
            "member_of": 6,
            "parallelism": 1,
        }
    )
    with pytest.raises(ExecutionPlanError, match="resource scheduling is not supported"):
        generate_plan(compilation.graph)
