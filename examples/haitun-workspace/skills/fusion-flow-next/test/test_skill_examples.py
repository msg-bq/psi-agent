from __future__ import annotations

import re
from pathlib import Path
from typing import cast

from fusion_flow_next import (
    Concept,
    Operator,
    ParseContext,
    WorkflowGraphCompilation,
    WorkflowGraphCompiler,
    parse_workflow,
)

_SKILL_PATH = Path(__file__).parents[1] / "SKILL.md"


def _context() -> ParseContext:
    concepts = {
        name: Concept(name)
        for name in (
            "Agent",
            "ApiBase",
            "Artifact",
            "Bool",
            "ComplexNumber",
            "Engine",
            "Executor",
            "Instruction",
            "Integer",
            "List",
            "Model",
            "ReasoningEffort",
            "Resource",
            "Step",
            "StepName",
            "Tool",
            "Workflow",
        )
    }
    signatures = {
        "agent_config": (("Agent", "Model", "Engine", "ApiBase"), "Bool"),
        "allowed_tool": (("Agent", "Tool"), "Bool"),
        "consumes": (("Step",), "List"),
        "foreach_item": (("Step", "List"), "Artifact"),
        "input_workflow": (("Workflow",), "List"),
        "max_attempts": (("Step",), "Integer"),
        "max_concurrency": (("Workflow",), "Integer"),
        "max_output_tokens": (("Agent",), "Integer"),
        "max_turns": (("Agent",), "Integer"),
        "output_workflow": (("Workflow",), "List"),
        "produces": (("Step",), "List"),
        "reasoning_effort": (("Agent",), "ReasoningEffort"),
        "resource_requirement": (("Step", "Resource"), "Integer"),
        "step_executor": (("Step",), "Executor"),
        "step_instruction": (("Step",), "Instruction"),
        "step_name": (("Step",), "StepName"),
        "step_timeout": (("Step",), "Integer"),
        "temperature": (("Agent",), "ComplexNumber"),
        "workflow_timeout": (("Workflow",), "Integer"),
    }
    return ParseContext(
        concepts=concepts,
        operators={
            name: Operator(
                name=name,
                input_concepts=tuple(concepts[concept_name] for concept_name in input_concepts),
                output_concept=concepts[output_concept],
            )
            for name, (input_concepts, output_concept) in signatures.items()
        },
    )


def test_per_item_skill_example_compiles_canonical_dataflow_lists() -> None:
    skill_text = _SKILL_PATH.read_text(encoding="utf-8")
    source = next(
        block
        for block in re.findall(r"```fusionflow\n(.*?)\n```", skill_text, re.DOTALL)
        if "workflow summarize_items" in block
    )

    parsed = parse_workflow(source, context=_context())

    assert parsed.diagnostics == ()
    assert parsed.core_ir is not None
    compiled = WorkflowGraphCompiler().compile(parsed.core_ir)
    compilation = cast(tuple[WorkflowGraphCompilation, ...], compiled)[0]
    assert compilation.residual_assertions == ()
