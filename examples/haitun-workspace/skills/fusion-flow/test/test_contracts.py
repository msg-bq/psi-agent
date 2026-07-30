from __future__ import annotations

import pytest
from fusion_flow import PlannedStep, check_planned_steps
from fusion_flow.checker import check_workflow
from fusion_flow.parser import parse_workflow
from fusion_flow.workflow_runner import _default_parse_context


def _check(source: str):
    parsed = parse_workflow(source, context=_default_parse_context())
    assert parsed.core_ir is not None
    return check_workflow(parsed.core_ir)


def test_checker_accepts_complete_workflow_and_string_step_name() -> None:
    result = _check(
        """
        const input: Artifact;
        const output: Artifact;
        const work: Step;
        const worker: Agent, Executor;
        workflow example {
          input_workflow(example) == [input];
          consumes(work) == [input];
          produces(work) == [output];
          output_workflow(example) == [output];
          step_executor(work) == worker;
          step_name(work) == "Readable Work";
          step_instruction(work) == "Produce output from input.";
        }
        """
    )

    assert result.diagnostics == ()


def test_checker_warns_for_legacy_name_suffix() -> None:
    result = _check(
        """
        const output: Artifact;
        const work: Step;
        const worker: Agent, Executor;
        const legacy_name: StepName;
        workflow example {
          input_workflow(example) == [];
          produces(work) == [output];
          output_workflow(example) == [output];
          step_executor(work) == worker;
          step_name(work) == legacy_name;
          step_instruction(work) == "Produce output.";
        }
        """
    )

    assert [(item.severity, item.message) for item in result.diagnostics] == [
        (
            "warning",
            "step 'work' uses symbolic display name 'legacy_name'; prefer a quoted string without the '_name' suffix",
        )
    ]


def test_checker_reports_missing_instruction() -> None:
    result = _check(
        """
        const output: Artifact;
        const work: Step;
        const worker: Agent, Executor;
        workflow example {
          input_workflow(example) == [];
          produces(work) == [output];
          output_workflow(example) == [output];
          step_executor(work) == worker;
          step_name(work) == "Work";
        }
        """
    )

    assert any(item.severity == "error" and "has no step_instruction" in item.message for item in result.diagnostics)


def test_checker_rejects_non_artifact_dataflow_values() -> None:
    result = _check(
        """
        const wrong_input: Step;
        const output: Artifact;
        const work: Step;
        const worker: Agent, Executor;
        workflow example {
          input_workflow(example) == [wrong_input];
          consumes(work) == [wrong_input];
          produces(work) == [output];
          output_workflow(example) == [output];
          step_executor(work) == worker;
          step_name(work) == "Work";
          step_instruction(work) == "Produce output.";
        }
        """
    )

    assert any(
        item.severity == "error" and item.message == "graph value 'wrong_input' must be declared as Artifact"
        for item in result.diagnostics
    )


def test_remaining_unimplemented_phase_boundary_fails_explicitly() -> None:
    with pytest.raises(NotImplementedError, match="planning check is not implemented"):
        check_planned_steps((PlannedStep("example", "Example step", ()),), ())
