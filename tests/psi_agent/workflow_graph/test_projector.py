from __future__ import annotations

from dataclasses import dataclass

import pytest

from psi_agent.workflow_graph.model import WorkflowGraphError
from psi_agent.workflow_graph.projector import (
    GraphProjectionError,
    WorkflowDialect,
    project_workflow,
)


@dataclass(frozen=True)
class Concept:
    name: str


@dataclass(frozen=True)
class Constant:
    symbol: str
    belong_concepts: tuple[Concept, ...] | None = None


@dataclass(frozen=True)
class Operator:
    name: str
    arity: int = 0


@dataclass(frozen=True)
class Compound:
    operator: Operator
    arguments: tuple[object, ...]


@dataclass(frozen=True)
class CompoundWithoutArguments:
    operator: Operator


@dataclass(frozen=True)
class CompoundWithMalformedOperator:
    operator: object
    arguments: tuple[object, ...]


@dataclass(frozen=True)
class Assertion:
    lhs: object
    rhs: object


@dataclass(frozen=True)
class Workflow:
    name: str
    assertions: tuple[object, ...]


@dataclass(frozen=True)
class RelationalAssertion:
    lhs: object
    rhs: object
    relation_symbol: object


@dataclass(frozen=True)
class ListValue:
    items: tuple[object, ...]


@dataclass(frozen=True)
class ElementListValue:
    elements: tuple[object, ...]


@dataclass(frozen=True)
class DualListValue:
    items: tuple[object, ...]
    elements: tuple[object, ...]


@dataclass(frozen=True)
class MemberSetValue:
    members: tuple[object, ...]


@dataclass(frozen=True)
class BareConstant:
    symbol: str


def test_projects_workflow_input() -> None:
    workflow = Workflow(
        name="workflow",
        assertions=(
            RelationalAssertion(
                lhs=Compound(
                    operator=Operator("input_workflow"),
                    arguments=(Constant("workflow"), Constant("input")),
                ),
                rhs=Constant("True"),
                relation_symbol="==",
            ),
        ),
    )

    projection = project_workflow(
        workflow,
        dialect=WorkflowDialect.REPOSITORY_LIST_MULTI,
    )

    assert projection.graph.to_dict()["artifacts"] == [
        {
            "artifact_id": "input",
            "is_input": True,
            "is_output": False,
            "binding_step_id": None,
        }
    ]


def _assertion(
    operator_name: str,
    arguments: tuple[object, ...],
    rhs: object,
) -> Assertion:
    return Assertion(
        lhs=Compound(
            operator=Operator(operator_name),
            arguments=arguments,
        ),
        rhs=rhs,
    )


@pytest.mark.parametrize(
    "lhs",
    (
        CompoundWithoutArguments(operator=Operator("unknown")),
        CompoundWithMalformedOperator(operator=object(), arguments=()),
    ),
)
def test_malformed_compound_is_not_silently_preserved_as_residual(lhs: object) -> None:
    workflow = Workflow(
        name="workflow",
        assertions=(Assertion(lhs=lhs, rhs=Constant("value")),),
    )

    with pytest.raises(GraphProjectionError):
        project_workflow(
            workflow,
            dialect=WorkflowDialect.REPOSITORY_LIST_MULTI,
        )


def test_integer_conversion_and_missing_step_diagnostics_use_public_deterministic_errors() -> None:
    oversized_integer = Workflow(
        name="workflow",
        assertions=(
            _assertion(
                "step_timeout",
                (Constant("step"),),
                Constant("9" * 5_000),
            ),
        ),
    )

    with pytest.raises(GraphProjectionError) as error:
        project_workflow(
            oversized_integer,
            dialect=WorkflowDialect.REPOSITORY_LIST_MULTI,
        )
    assert isinstance(error.value.__cause__, ValueError)

    missing_metadata = Workflow(
        name="workflow",
        assertions=(
            _assertion("step_instruction", (Constant("b"),), Constant("instruction")),
            _assertion("step_instruction", (Constant("a"),), Constant("instruction")),
        ),
    )

    with pytest.raises(GraphProjectionError, match="step 'a' has no step_name"):
        project_workflow(
            missing_metadata,
            dialect=WorkflowDialect.REPOSITORY_LIST_MULTI,
        )


def test_projects_all_scalar_operators() -> None:
    workflow = Workflow(
        name="workflow",
        assertions=(
            _assertion(
                "input_workflow",
                (Constant("workflow"), Constant("input")),
                Constant("True"),
            ),
            _assertion(
                "output_workflow",
                (Constant("workflow"), Constant("output")),
                Constant("True"),
            ),
            _assertion("step_name", (Constant("step"),), Constant("name")),
            _assertion(
                "step_instruction",
                (Constant("step"),),
                Constant("instruction"),
            ),
            _assertion(
                "step_executor",
                (Constant("step"),),
                Constant("executor", (Concept("Agent"),)),
            ),
            _assertion(
                "consumes",
                (Constant("step"), Constant("input")),
                Constant("True"),
            ),
            _assertion(
                "produces",
                (Constant("step"), Constant("output")),
                Constant("True"),
            ),
            _assertion(
                "foreach_item",
                (Constant("step"), Constant("input")),
                Constant("item"),
            ),
            _assertion("step_timeout", (Constant("step"),), Constant("30")),
            _assertion("max_attempts", (Constant("step"),), Constant("2")),
            _assertion(
                "resource_requirement",
                (Constant("step"), Constant("gpu")),
                Constant("3"),
            ),
            _assertion(
                "max_concurrency",
                (Constant("workflow"),),
                Constant("4"),
            ),
            _assertion(
                "workflow_timeout",
                (Constant("workflow"),),
                Constant("120"),
            ),
        ),
    )

    projection = project_workflow(
        workflow,
        dialect=WorkflowDialect.REPOSITORY_LIST_MULTI,
    )

    assert projection.residual_assertions == ()
    assert projection.graph.to_dict() == {
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
    assert not hasattr(projection.graph.steps[0], "executor_kind")


def test_recognized_operator_wraps_malformed_relation_as_projection_error() -> None:
    workflow = Workflow(
        name="workflow",
        assertions=(
            RelationalAssertion(
                lhs=Compound(
                    operator=Operator("input_workflow"),
                    arguments=(Constant("workflow"), Constant("input")),
                ),
                rhs=Constant("True"),
                relation_symbol=[],
            ),
        ),
    )

    with pytest.raises(GraphProjectionError, match="requires equality"):
        project_workflow(
            workflow,
            dialect=WorkflowDialect.REPOSITORY_LIST_MULTI,
        )


def _step_declarations(
    *,
    step_id: str = "step",
    executor: object = BareConstant("executor"),
) -> tuple[Assertion, ...]:
    return (
        _assertion("step_name", (Constant(step_id),), Constant(f"{step_id}-name")),
        _assertion("step_executor", (Constant(step_id),), executor),
    )


def test_executor_metadata_is_optional_but_unambiguous_when_present() -> None:
    for executor in (
        BareConstant("executor"),
        Constant("executor", None),
        Constant("executor", ()),
        Constant("executor", (Concept("Human"),)),
        Constant("executor", (Concept("Agent"),)),
        Constant("executor", (Concept("Program"),)),
    ):
        projection = project_workflow(
            Workflow(
                name="workflow",
                assertions=_step_declarations(executor=executor),
            ),
            dialect=WorkflowDialect.REPOSITORY_LIST_MULTI,
        )
        assert projection.graph.steps[0].executor_id == "executor"

    for concepts in (
        (Concept("Other"),),
        (Concept("Human"), Concept("Agent")),
    ):
        with pytest.raises(GraphProjectionError, match="exactly one"):
            project_workflow(
                Workflow(
                    name="workflow",
                    assertions=_step_declarations(
                        executor=Constant("executor", concepts),
                    ),
                ),
                dialect=WorkflowDialect.REPOSITORY_LIST_MULTI,
            )


def test_scalar_validation_rejects_bad_owner_arity_rhs_and_duplicates() -> None:
    invalid_assertions = (
        _assertion(
            "input_workflow",
            (Constant("other"), Constant("input")),
            Constant("True"),
        ),
        _assertion(
            "input_workflow",
            (Constant("workflow"),),
            Constant("True"),
        ),
        _assertion(
            "input_workflow",
            (Constant("workflow"), Constant("input")),
            Constant("yes"),
        ),
        _assertion("step_timeout", (Constant("step"),), Constant("0")),
        _assertion("max_attempts", (Constant("step"),), Constant("1.5")),
        _assertion(
            "resource_requirement",
            (Constant("step"), Constant("gpu")),
            Constant("-1"),
        ),
    )
    for assertion in invalid_assertions:
        with pytest.raises(GraphProjectionError):
            project_workflow(
                Workflow(name="workflow", assertions=(assertion,)),
                dialect=WorkflowDialect.REPOSITORY_LIST_MULTI,
            )

    duplicate_groups = (
        (
            _assertion(
                "input_workflow",
                (Constant("workflow"), Constant("input")),
                Constant("True"),
            ),
        )
        * 2,
        (
            *_step_declarations(),
            _assertion("step_name", (Constant("step"),), Constant("other-name")),
        ),
        (
            *_step_declarations(),
            _assertion(
                "resource_requirement",
                (Constant("step"), Constant("gpu")),
                Constant("1"),
            ),
            _assertion(
                "resource_requirement",
                (Constant("step"), Constant("gpu")),
                Constant("1"),
            ),
        ),
        (
            *_step_declarations(),
            _assertion(
                "input_workflow",
                (Constant("workflow"), Constant("input")),
                Constant("True"),
            ),
            _assertion(
                "consumes",
                (Constant("step"), Constant("input")),
                Constant("True"),
            ),
            _assertion(
                "consumes",
                (Constant("step"), Constant("input")),
                Constant("True"),
            ),
        ),
    )
    for assertions in duplicate_groups:
        with pytest.raises(GraphProjectionError, match="duplicate"):
            project_workflow(
                Workflow(name="workflow", assertions=assertions),
                dialect=WorkflowDialect.REPOSITORY_LIST_MULTI,
            )


def test_unknown_top_level_assertion_and_ordinary_list_remain_residual() -> None:
    unknown = RelationalAssertion(
        lhs=Compound(
            operator=Operator("value_assignment"),
            arguments=(Constant("files"),),
        ),
        rhs=ListValue((Constant("a"), Constant("b"))),
        relation_symbol="<",
    )
    known_only_on_rhs = Assertion(
        lhs=Constant("x"),
        rhs=Compound(
            operator=Operator("input_workflow"),
            arguments=(Constant("workflow"), Constant("input")),
        ),
    )
    projection = project_workflow(
        Workflow(
            name="workflow",
            assertions=(unknown, known_only_on_rhs),
        ),
        dialect=WorkflowDialect.REPOSITORY_LIST_MULTI,
    )

    assert projection.residual_assertions == (unknown, known_only_on_rhs)
    assert projection.graph.artifacts == ()


def test_projection_is_order_independent_and_allows_a_cycle() -> None:
    assertions = (
        *_step_declarations(step_id="a"),
        *_step_declarations(step_id="b"),
        _assertion(
            "consumes",
            (Constant("a"), Constant("from-b")),
            Constant("True"),
        ),
        _assertion(
            "produces",
            (Constant("a"), Constant("from-a")),
            Constant("True"),
        ),
        _assertion(
            "consumes",
            (Constant("b"), Constant("from-a")),
            Constant("True"),
        ),
        _assertion(
            "produces",
            (Constant("b"), Constant("from-b")),
            Constant("True"),
        ),
    )
    left = project_workflow(
        Workflow(name="workflow", assertions=assertions),
        dialect=WorkflowDialect.REPOSITORY_LIST_MULTI,
    )
    right = project_workflow(
        Workflow(name="workflow", assertions=tuple(reversed(assertions))),
        dialect=WorkflowDialect.REPOSITORY_LIST_MULTI,
    )

    assert left.graph.to_dict() == right.graph.to_dict()
    assert len(left.graph.edges) == 4


def test_resource_keys_do_not_collide_when_identities_contain_colons() -> None:
    projection = project_workflow(
        Workflow(
            name="workflow",
            assertions=(
                *_step_declarations(step_id="a:b"),
                *_step_declarations(step_id="a"),
                _assertion(
                    "resource_requirement",
                    (Constant("a:b"), Constant("c")),
                    Constant("1"),
                ),
                _assertion(
                    "resource_requirement",
                    (Constant("a"), Constant("b:c")),
                    Constant("2"),
                ),
            ),
        ),
        dialect=WorkflowDialect.REPOSITORY_LIST_MULTI,
    )

    assert {
        (step.step_id, requirement.resource_id, requirement.amount)
        for step in projection.graph.steps
        for requirement in step.resources
    } == {("a:b", "c", 1), ("a", "b:c", 2)}


def test_graph_validation_error_is_wrapped_and_chained() -> None:
    with pytest.raises(GraphProjectionError) as caught:
        project_workflow(
            Workflow(
                name="workflow",
                assertions=(
                    _assertion(
                        "output_workflow",
                        (Constant("workflow"), Constant("missing")),
                        Constant("True"),
                    ),
                ),
            ),
            dialect=WorkflowDialect.REPOSITORY_LIST_MULTI,
        )

    assert isinstance(caught.value.__cause__, WorkflowGraphError)


def _repository_multi_workflow(
    *,
    inputs: tuple[str, ...] = ("in-a", "in-b"),
    outputs: tuple[str, ...] = ("out-a", "out-b"),
) -> Workflow:
    return Workflow(
        name="workflow",
        assertions=(
            *_step_declarations(),
            _assertion(
                "input_workflow_multi",
                (Constant("workflow"),),
                ListValue(tuple(Constant(item) for item in inputs)),
            ),
            _assertion(
                "output_workflow_multi",
                (Constant("workflow"),),
                ElementListValue(tuple(Constant(item) for item in outputs)),
            ),
            _assertion(
                "consumes_multi",
                (Constant("step"),),
                ListValue(tuple(Constant(item) for item in inputs)),
            ),
            _assertion(
                "produces_multi",
                (Constant("step"),),
                ElementListValue(tuple(Constant(item) for item in outputs)),
            ),
        ),
    )


def test_repository_multi_projects_all_four_relation_carriers() -> None:
    projection = project_workflow(
        _repository_multi_workflow(),
        dialect=WorkflowDialect.REPOSITORY_LIST_MULTI,
    )

    assert {
        (artifact.artifact_id, artifact.is_input, artifact.is_output) for artifact in projection.graph.artifacts
    } == {
        ("in-a", True, False),
        ("in-b", True, False),
        ("out-a", False, True),
        ("out-b", False, True),
    }
    assert {(edge.kind, edge.artifact_id, edge.step_id) for edge in projection.graph.edges} == {
        ("consumes", "in-a", "step"),
        ("consumes", "in-b", "step"),
        ("produces", "out-a", "step"),
        ("produces", "out-b", "step"),
    }


def test_repository_multi_erases_carrier_order() -> None:
    left = project_workflow(
        _repository_multi_workflow(),
        dialect=WorkflowDialect.REPOSITORY_LIST_MULTI,
    )
    right = project_workflow(
        _repository_multi_workflow(
            inputs=("in-b", "in-a"),
            outputs=("out-b", "out-a"),
        ),
        dialect=WorkflowDialect.REPOSITORY_LIST_MULTI,
    )

    assert left.graph.to_dict() == right.graph.to_dict()


def test_repository_multi_rejects_duplicates_and_conflicting_dual_fields() -> None:
    duplicate = Workflow(
        name="workflow",
        assertions=(
            _assertion(
                "input_workflow_multi",
                (Constant("workflow"),),
                ListValue((Constant("a"), Constant("a"))),
            ),
        ),
    )
    conflicting = Workflow(
        name="workflow",
        assertions=(
            _assertion(
                "input_workflow_multi",
                (Constant("workflow"),),
                DualListValue(
                    items=(Constant("a"), Constant("b")),
                    elements=(Constant("b"), Constant("a")),
                ),
            ),
        ),
    )
    for workflow in (duplicate, conflicting):
        with pytest.raises(GraphProjectionError):
            project_workflow(
                workflow,
                dialect=WorkflowDialect.REPOSITORY_LIST_MULTI,
            )


def test_repository_multi_accepts_matching_dual_fields_and_empty_lists() -> None:
    carrier = (Constant("input"),)
    matching = Workflow(
        name="workflow",
        assertions=(
            _assertion(
                "input_workflow_multi",
                (Constant("workflow"),),
                DualListValue(items=carrier, elements=carrier),
            ),
        ),
    )
    empty = Workflow(
        name="workflow",
        assertions=tuple(
            _assertion(
                operator_name,
                (Constant("workflow"),) if operator_name.startswith(("input_", "output_")) else (Constant("step"),),
                ListValue(()),
            )
            for operator_name in (
                "input_workflow_multi",
                "output_workflow_multi",
            )
        ),
    )

    assert (
        project_workflow(
            matching,
            dialect=WorkflowDialect.REPOSITORY_LIST_MULTI,
        )
        .graph.artifacts[0]
        .is_input
    )
    assert (
        project_workflow(
            empty,
            dialect=WorkflowDialect.REPOSITORY_LIST_MULTI,
        ).graph.artifacts
        == ()
    )


def test_syntax_review_multi_accepts_only_members_consumes() -> None:
    assertions = (
        *_step_declarations(),
        _assertion(
            "input_workflow",
            (Constant("workflow"), Constant("a")),
            Constant("True"),
        ),
        _assertion(
            "input_workflow",
            (Constant("workflow"), Constant("b")),
            Constant("True"),
        ),
        _assertion(
            "consumes_multi",
            (Constant("step"),),
            MemberSetValue((Constant("b"), Constant("a"))),
        ),
    )

    projection = project_workflow(
        Workflow(name="workflow", assertions=assertions),
        dialect=WorkflowDialect.SYNTAX_REVIEW_2026_07_18,
    )

    assert {(edge.artifact_id, edge.step_id) for edge in projection.graph.edges} == {("a", "step"), ("b", "step")}


def test_multi_forms_are_rejected_across_dialects() -> None:
    repository_form = Workflow(
        name="workflow",
        assertions=(
            *_step_declarations(),
            _assertion(
                "consumes_multi",
                (Constant("step"),),
                ListValue(()),
            ),
        ),
    )
    review_form = Workflow(
        name="workflow",
        assertions=(
            *_step_declarations(),
            _assertion(
                "consumes_multi",
                (Constant("step"),),
                MemberSetValue(()),
            ),
        ),
    )
    review_unsupported_operator = Workflow(
        name="workflow",
        assertions=(
            _assertion(
                "input_workflow_multi",
                (Constant("workflow"),),
                MemberSetValue(()),
            ),
        ),
    )
    cases = (
        (repository_form, WorkflowDialect.SYNTAX_REVIEW_2026_07_18),
        (review_form, WorkflowDialect.REPOSITORY_LIST_MULTI),
        (
            review_unsupported_operator,
            WorkflowDialect.SYNTAX_REVIEW_2026_07_18,
        ),
    )
    for workflow, dialect in cases:
        with pytest.raises(GraphProjectionError):
            project_workflow(workflow, dialect=dialect)


def test_scalar_and_multi_relations_share_duplicate_detection() -> None:
    workflow = Workflow(
        name="workflow",
        assertions=(
            _assertion(
                "input_workflow",
                (Constant("workflow"), Constant("input")),
                Constant("True"),
            ),
            _assertion(
                "input_workflow_multi",
                (Constant("workflow"),),
                ListValue((Constant("input"),)),
            ),
        ),
    )

    with pytest.raises(GraphProjectionError, match="duplicate"):
        project_workflow(
            workflow,
            dialect=WorkflowDialect.REPOSITORY_LIST_MULTI,
        )
