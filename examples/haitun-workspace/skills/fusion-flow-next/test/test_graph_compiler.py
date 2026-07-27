from __future__ import annotations

from typing import cast

import fusion_flow_next
import pytest
from fusion_flow_next.compiler import CoreIRCompiler
from fusion_flow_next.core_ir import (
    Assertion,
    CompoundTerm,
    Concept,
    Constant,
    IfTerm,
    ListTerm,
    Operator,
    Term,
    Workflow,
    WorkflowFile,
)
from fusion_flow_next.graph_compiler import (
    ValueSource,
    WorkflowGraphCompilation,
    WorkflowGraphCompilationError,
    WorkflowGraphCompiler,
)

from psi_agent.workflow_graph.model import WorkflowGraphError


def _assertion(
    operator_name: str,
    arguments: tuple[Term, ...],
    rhs: Term,
) -> Assertion:
    return Assertion(
        lhs=CompoundTerm(
            operator=Operator(operator_name),
            arguments=arguments,
        ),
        rhs=rhs,
    )


def _step_declarations(step_id: str = "step") -> tuple[Assertion, ...]:
    step = Constant(step_id)
    return (
        _assertion("step_name", (step,), Constant(f"{step_id}-name")),
        _assertion(
            "step_executor",
            (step,),
            Constant(f"{step_id}-executor", (Concept("Agent"),)),
        ),
    )


def _compile(
    assertions: tuple[Assertion, ...],
    *,
    workflow_id: str = "workflow",
) -> WorkflowGraphCompilation:
    compiled = WorkflowGraphCompiler().compile(
        WorkflowFile(
            constants=(),
            workflows=(Workflow(name=workflow_id, assertions=assertions),),
        )
    )
    assert isinstance(compiled, tuple)
    return cast(tuple[WorkflowGraphCompilation, ...], compiled)[0]


def test_compiles_all_graph_operators() -> None:
    workflow = Constant("workflow")
    step = Constant("step")
    input_artifact = Constant("input")
    output_artifact = Constant("output")
    compilation = _compile(
        (
            _assertion("input_workflow", (workflow,), ListTerm((input_artifact,))),
            _assertion("output_workflow", (workflow,), ListTerm((output_artifact,))),
            _assertion("step_name", (step,), Constant("name")),
            _assertion("step_instruction", (step,), Constant("instruction")),
            _assertion(
                "step_executor",
                (step,),
                Constant("executor", (Concept("Agent"),)),
            ),
            _assertion("consumes", (step,), ListTerm((input_artifact,))),
            _assertion("produces", (step,), ListTerm((output_artifact,))),
            _assertion("foreach_item", (step, input_artifact), Constant("item")),
            _assertion("step_timeout", (step,), Constant("30")),
            _assertion("max_attempts", (step,), Constant("2")),
            _assertion(
                "resource_requirement",
                (step, Constant("gpu")),
                Constant("3"),
            ),
            _assertion("max_concurrency", (workflow,), Constant("4")),
            _assertion("workflow_timeout", (workflow,), Constant("120")),
        )
    )

    assert compilation.residual_assertions == ()
    assert compilation.graph.to_dict() == {
        "workflow_id": "workflow",
        "steps": [
            {
                "step_id": "step",
                "name_id": "name",
                "executor_id": "executor",
                "instruction_id": "instruction",
                "timeout_seconds": 30,
                "max_attempts": 2,
                "resources": [{"resource_id": "gpu", "amount": 3}],
            }
        ],
        "artifacts": [
            {
                "artifact_id": "input",
                "is_input": True,
                "is_output": False,
                "binding_step_id": None,
            },
            {
                "artifact_id": "item",
                "is_input": False,
                "is_output": False,
                "binding_step_id": "step",
            },
            {
                "artifact_id": "output",
                "is_input": False,
                "is_output": True,
                "binding_step_id": None,
            },
        ],
        "edges": [
            {"kind": "consumes", "artifact_id": "input", "step_id": "step"},
            {
                "kind": "foreach",
                "artifact_id": "input",
                "step_id": "step",
                "item_binding_id": "item",
            },
            {"kind": "produces", "step_id": "step", "artifact_id": "output"},
        ],
        "policy": {"max_concurrency": 4, "timeout_seconds": 120},
    }


def test_graph_dataflow_operators_read_multiple_list_term_items() -> None:
    workflow = Constant("workflow")
    step = Constant("step")
    inputs = (Constant("in-b"), Constant("in-a"))
    outputs = (Constant("out-b"), Constant("out-a"))
    compilation = _compile(
        (
            *_step_declarations(),
            _assertion("input_workflow", (workflow,), ListTerm(inputs)),
            _assertion("output_workflow", (workflow,), ListTerm(outputs)),
            _assertion("consumes", (step,), ListTerm(inputs)),
            _assertion("produces", (step,), ListTerm(outputs)),
        )
    )

    assert {
        (artifact.artifact_id, artifact.is_input, artifact.is_output) for artifact in compilation.graph.artifacts
    } == {
        ("in-a", True, False),
        ("in-b", True, False),
        ("out-a", False, True),
        ("out-b", False, True),
    }
    assert {(edge.kind, edge.artifact_id, edge.step_id) for edge in compilation.graph.edges} == {
        ("consumes", "in-a", "step"),
        ("consumes", "in-b", "step"),
        ("produces", "out-a", "step"),
        ("produces", "out-b", "step"),
    }


def test_shared_compiler_contract_builds_every_workflow() -> None:
    compiler = WorkflowGraphCompiler()

    compiled = compiler.compile(
        WorkflowFile(
            constants=(),
            workflows=(
                Workflow(name="first", assertions=()),
                Workflow(name="second", assertions=()),
            ),
        )
    )
    assert isinstance(compiled, tuple)
    compilations = cast(tuple[WorkflowGraphCompilation, ...], compiled)

    assert isinstance(compiler, CoreIRCompiler)
    assert tuple(compilation.graph.workflow_id for compilation in compilations) == (
        "first",
        "second",
    )


def test_unknown_assertions_remain_residual() -> None:
    unknown = _assertion(
        "value_assignment",
        (Constant("files"),),
        ListTerm((Constant("a"), Constant("b"))),
    )
    reversed_unknown = Assertion(
        lhs=Constant("value"),
        rhs=CompoundTerm(
            operator=Operator("value_assignment"),
            arguments=(Constant("files"),),
        ),
    )
    ordinary_equality = Assertion(lhs=Constant("left"), rhs=Constant("right"))

    compilation = _compile((unknown, reversed_unknown, ordinary_equality))

    assert compilation.graph.steps == ()
    assert compilation.graph.artifacts == ()
    assert compilation.residual_assertions == (
        unknown,
        reversed_unknown,
        ordinary_equality,
    )


def test_value_from_lowers_to_an_implicit_workflow_input() -> None:
    value = Constant("request")
    compilation = _compile(
        (
            *_step_declarations(),
            _assertion("consumes", (Constant("step"),), ListTerm((value,))),
            _assertion("value_from", (value,), Constant("request-source")),
        )
    )

    assert compilation.value_sources == (ValueSource(value_id="request", source_id="request-source"),)
    assert tuple(
        (artifact.artifact_id, artifact.is_input, artifact.is_output) for artifact in compilation.graph.artifacts
    ) == (("request", True, False),)
    assert tuple(edge.kind for edge in compilation.graph.edges) == ("consumes",)
    assert compilation.residual_assertions == ()


def test_value_from_is_order_independent_and_sorted() -> None:
    values = (Constant("value-b"), Constant("value-a"))
    reversed_source = Assertion(
        lhs=Constant("source-b"),
        rhs=CompoundTerm(
            operator=Operator("value_from"),
            arguments=(values[0],),
        ),
    )
    assertions = (
        *_step_declarations(),
        _assertion("consumes", (Constant("step"),), ListTerm(values)),
        reversed_source,
        _assertion("value_from", (values[1],), Constant("source-a")),
    )

    forward = _compile(assertions)
    backward = _compile(tuple(reversed(assertions)))

    assert (
        forward.value_sources
        == backward.value_sources
        == (
            ValueSource(value_id="value-a", source_id="source-a"),
            ValueSource(value_id="value-b", source_id="source-b"),
        )
    )
    assert forward.graph.to_dict() == backward.graph.to_dict()


def test_value_from_may_repeat_an_explicit_workflow_input() -> None:
    value = Constant("request")
    compilation = _compile(
        (
            *_step_declarations(),
            _assertion(
                "input_workflow",
                (Constant("workflow"),),
                ListTerm((value,)),
            ),
            _assertion("consumes", (Constant("step"),), ListTerm((value,))),
            _assertion("value_from", (value,), Constant("request-source")),
        )
    )

    assert compilation.value_sources == (ValueSource(value_id="request", source_id="request-source"),)
    assert compilation.graph.artifacts[0].is_input


def test_value_from_may_supply_a_workflow_output_without_a_consumer() -> None:
    value = Constant("result")
    compilation = _compile(
        (
            _assertion(
                "output_workflow",
                (Constant("workflow"),),
                ListTerm((value,)),
            ),
            _assertion("value_from", (value,), Constant("result-source")),
        )
    )

    assert compilation.graph.artifacts[0].is_input
    assert compilation.graph.artifacts[0].is_output
    assert compilation.graph.edges == ()


def test_duplicate_value_from_is_rejected() -> None:
    with pytest.raises(
        WorkflowGraphCompilationError,
        match="duplicate value_from: 'request'",
    ):
        _compile(
            (
                _assertion(
                    "output_workflow",
                    (Constant("workflow"),),
                    ListTerm((Constant("request"),)),
                ),
                _assertion(
                    "value_from",
                    (Constant("request"),),
                    Constant("first-source"),
                ),
                _assertion(
                    "value_from",
                    (Constant("request"),),
                    Constant("second-source"),
                ),
            )
        )


def test_value_from_cannot_bind_a_produced_value() -> None:
    with pytest.raises(
        WorkflowGraphCompilationError,
        match="value_from value cannot be produced: 'result'",
    ):
        _compile(
            (
                *_step_declarations(),
                _assertion(
                    "produces",
                    (Constant("step"),),
                    ListTerm((Constant("result"),)),
                ),
                _assertion(
                    "value_from",
                    (Constant("result"),),
                    Constant("result-source"),
                ),
            )
        )


def test_value_from_value_must_be_consumed_or_a_workflow_output() -> None:
    with pytest.raises(
        WorkflowGraphCompilationError,
        match="value_from value must be consumed or a workflow output: 'unused'",
    ):
        _compile(
            (
                _assertion(
                    "value_from",
                    (Constant("unused"),),
                    Constant("unused-source"),
                ),
            )
        )


def test_executor_configuration_remains_residual() -> None:
    program_path = _assertion(
        "program_path",
        (Constant("program"),),
        Constant("program-source"),
    )
    agent_system_prompt = _assertion(
        "agent_system_prompt",
        (Constant("agent"),),
        Constant("system-prompt"),
    )

    compilation = _compile((program_path, agent_system_prompt))

    assert compilation.value_sources == ()
    assert compilation.residual_assertions == (
        program_path,
        agent_system_prompt,
    )


def test_supported_graph_operator_on_rhs_is_lowered_as_equality() -> None:
    reversed_input = Assertion(
        lhs=ListTerm((Constant("artifact2"),)),
        rhs=CompoundTerm(
            operator=Operator("input_workflow"),
            arguments=(Constant("workflow1"),),
        ),
    )

    compilation = _compile((reversed_input,), workflow_id="workflow1")

    assert compilation.residual_assertions == ()
    assert tuple(
        (artifact.artifact_id, artifact.is_input, artifact.is_output) for artifact in compilation.graph.artifacts
    ) == (("artifact2", True, False),)


def test_one_equality_cannot_declare_multiple_graph_facts() -> None:
    assertion = Assertion(
        lhs=CompoundTerm(
            operator=Operator("input_workflow"),
            arguments=(Constant("workflow"),),
        ),
        rhs=CompoundTerm(
            operator=Operator("output_workflow"),
            arguments=(Constant("workflow"),),
        ),
    )

    with pytest.raises(
        WorkflowGraphCompilationError,
        match="one equality cannot declare multiple graph facts",
    ):
        _compile((assertion,))


def test_supported_operator_with_unsupported_term_fails_closed() -> None:
    conditional = IfTerm(
        condition=Assertion(lhs=Constant("condition"), rhs=Constant("True")),
        when_true=Constant("yes"),
        when_false=Constant("no"),
    )

    with pytest.raises(ValueError, match="unsupported if term"):
        _compile((_assertion("step_name", (Constant("step"),), conditional),))


def test_oversized_integer_is_reported_as_a_graph_compilation_error() -> None:
    with pytest.raises(
        WorkflowGraphCompilationError,
        match="step_timeout RHS must be a positive integer constant",
    ) as caught:
        _compile(
            (
                *_step_declarations(),
                _assertion(
                    "step_timeout",
                    (Constant("step"),),
                    Constant("9" * 5000),
                ),
            )
        )

    assert isinstance(caught.value.__cause__, ValueError)


def test_explicit_one_does_not_hide_duplicate_max_attempts() -> None:
    with pytest.raises(WorkflowGraphCompilationError, match="duplicate max_attempts"):
        _compile(
            (
                *_step_declarations(),
                _assertion("max_attempts", (Constant("step"),), Constant("1")),
                _assertion("max_attempts", (Constant("step"),), Constant("2")),
            )
        )


def test_cycle_compilation_is_order_independent() -> None:
    assertions = (
        *_step_declarations("a"),
        *_step_declarations("b"),
        _assertion(
            "consumes",
            (Constant("a"),),
            ListTerm((Constant("from-b"),)),
        ),
        _assertion(
            "produces",
            (Constant("a"),),
            ListTerm((Constant("from-a"),)),
        ),
        _assertion(
            "consumes",
            (Constant("b"),),
            ListTerm((Constant("from-a"),)),
        ),
        _assertion(
            "produces",
            (Constant("b"),),
            ListTerm((Constant("from-b"),)),
        ),
    )

    left = _compile(assertions)
    right = _compile(tuple(reversed(assertions)))

    assert left.graph.to_dict() == right.graph.to_dict()
    assert len(left.graph.edges) == 4


def test_graph_validation_errors_are_public_and_chained() -> None:
    with pytest.raises(
        WorkflowGraphCompilationError,
        match="input or producer-backed",
    ) as caught:
        _compile(
            (
                _assertion(
                    "output_workflow",
                    (Constant("workflow"),),
                    ListTerm((Constant("missing"),)),
                ),
            )
        )

    assert isinstance(caught.value.__cause__, WorkflowGraphError)


def test_graph_backend_is_exported_from_package() -> None:
    assert fusion_flow_next.ValueSource is ValueSource
    assert fusion_flow_next.WorkflowGraphCompiler is WorkflowGraphCompiler
    assert fusion_flow_next.WorkflowGraphCompilation is WorkflowGraphCompilation
    assert fusion_flow_next.WorkflowGraphCompilationError is WorkflowGraphCompilationError
