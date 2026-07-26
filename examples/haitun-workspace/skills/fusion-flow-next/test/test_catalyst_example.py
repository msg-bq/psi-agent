from __future__ import annotations

import importlib.util
import os
import re
import sys
from collections import Counter
from typing import Any, cast

import pytest

_EXAMPLE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "examples",
    "catalyst",
)
_WORKFLOW_PATH = os.path.join(_EXAMPLE_DIR, "catalyst.workflow")

_SKILL_DIR = os.path.dirname(os.path.dirname(__file__))
_PACKAGE_DIR = os.path.join(_SKILL_DIR, "fusion_flow_next")


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
WorkflowGraphCompilationError = fusion_flow_next.WorkflowGraphCompilationError
WorkflowGraphCompiler = fusion_flow_next.WorkflowGraphCompiler


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

    assert len(instruction_paths) == len(instruction_relations) == 11
    assert set(instruction_paths) == {
        "./instructions/analyze-route-feasibility.md",
        "./instructions/design-synthesis-route.md",
        "./instructions/evaluate-structures.md",
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

    producer_counts = Counter(
        assertion.lhs.arguments[1].symbol
        for assertion in result.core_ir.workflows[0].assertions
        if isinstance(assertion.lhs, CompoundTerm)
        and assertion.lhs.operator.name == "produces"
        and isinstance(assertion.lhs.arguments[1], Constant)
        and isinstance(assertion.rhs, Constant)
        and assertion.rhs.symbol == "True"
    )
    assert producer_counts["candidate_catalyst_structure_pool"] == 3
    assert producer_counts["candidate_catalyst_pool"] == 3
    assert producer_counts["tmp_candidates_directory"] == 6
    assert producer_counts["tmp_knowledge_directory"] == 5

    with pytest.raises(
        WorkflowGraphCompilationError,
        match="artifact has multiple producers",
    ) as raised:
        WorkflowGraphCompiler().compile(result.core_ir)

    assert str(raised.value) == ("artifact has multiple producers: candidate_catalyst_structure_pool")
