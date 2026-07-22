from __future__ import annotations

from fusion_flow_next.core_ir import (
    Assertion,
    CompoundTerm,
    ConnectiveFormula,
    Constant,
    IfTerm,
    ListTerm,
    WorkflowFile,
)
from fusion_flow_next.parser import parse_workflow


def test_parse_workflow_lowers_complete_surface_to_core_ir() -> None:
    result = parse_workflow(
        """
        const review: Step, Agent;
        const "draft": Artifact;
        const backup: Agent;

        workflow first {
          custom(agent, review) == TRUE;
          custom(review) == False;
        }

        workflow second {
          step_executor(review) == if(!(max_attempts(review) != 2) AND max_turns(agent) = 8, writer, human);
          custom(1 + 2 * 3, [review, "draft"], -(4 ^ 2 ^ 3)) == true;
        }
        """
    )

    assert result.diagnostics == ()
    assert isinstance(result.core_ir, WorkflowFile)
    workflow_file = result.core_ir
    assert [constant.symbol for constant in workflow_file.constants] == ["review", "draft", "backup"]
    assert [workflow.name for workflow in workflow_file.workflows] == ["first", "second"]

    review, draft, backup = workflow_file.constants
    assert review.belong_concepts[1] is backup.belong_concepts[0]

    first_workflow, second_workflow = workflow_file.workflows
    first_custom_assertion, second_custom_assertion = first_workflow.assertions
    conditional_assertion, arithmetic_assertion = second_workflow.assertions
    assert all(
        assertion.relation_symbol == "="
        for assertion in (
            first_custom_assertion,
            second_custom_assertion,
            conditional_assertion,
            arithmetic_assertion,
        )
    )

    assert isinstance(first_custom_assertion.lhs, CompoundTerm)
    assert isinstance(second_custom_assertion.lhs, CompoundTerm)
    assert isinstance(arithmetic_assertion.lhs, CompoundTerm)
    first_custom = first_custom_assertion.lhs
    second_custom = second_custom_assertion.lhs
    arithmetic_call = arithmetic_assertion.lhs
    assert first_custom.operator.name == "custom"
    assert first_custom.operator is second_custom.operator
    assert first_custom.operator is arithmetic_call.operator
    assert first_custom.arguments[1] is review
    assert second_custom.arguments[0] is review

    assert isinstance(first_custom_assertion.rhs, Constant)
    assert isinstance(second_custom_assertion.rhs, Constant)
    assert first_custom_assertion.rhs.symbol == "true"
    assert second_custom_assertion.rhs.symbol == "false"
    assert arithmetic_assertion.rhs is first_custom_assertion.rhs

    assert isinstance(conditional_assertion.lhs, CompoundTerm)
    assert conditional_assertion.lhs.operator.name == "step_executor"
    assert conditional_assertion.lhs.arguments[0] is review
    assert isinstance(conditional_assertion.rhs, IfTerm)
    conditional = conditional_assertion.rhs
    assert isinstance(conditional.condition, ConnectiveFormula)
    assert conditional.condition.connective == "AND"
    assert isinstance(conditional.condition.formula_left, ConnectiveFormula)
    negated = conditional.condition.formula_left
    assert negated.connective == "NOT"
    assert negated.formula_right is None
    assert isinstance(negated.formula_left, Assertion)
    not_equals = negated.formula_left
    assert not_equals.relation_symbol == "!="
    assert isinstance(not_equals.lhs, CompoundTerm)
    assert not_equals.lhs.operator.name == "max_attempts"
    assert not_equals.lhs.arguments[0] is review
    assert isinstance(not_equals.rhs, Constant)
    assert not_equals.rhs.symbol == "2"

    assert isinstance(conditional.condition.formula_right, Assertion)
    numeric_equals = conditional.condition.formula_right
    assert numeric_equals.relation_symbol == "="
    assert isinstance(numeric_equals.lhs, CompoundTerm)
    assert numeric_equals.lhs.operator.name == "max_turns"
    assert numeric_equals.lhs.arguments[0] is first_custom.arguments[0]
    assert isinstance(numeric_equals.rhs, Constant)
    assert numeric_equals.rhs.symbol == "8"
    assert isinstance(conditional.when_true, Constant)
    assert isinstance(conditional.when_false, Constant)
    assert conditional.when_true.symbol == "writer"
    assert conditional.when_false.symbol == "human"

    sum_term, list_term, negation = arithmetic_call.arguments
    assert isinstance(sum_term, CompoundTerm)
    assert sum_term.operator.name == "+"
    assert isinstance(sum_term.arguments[0], Constant)
    assert sum_term.arguments[0].symbol == "1"
    assert isinstance(sum_term.arguments[1], CompoundTerm)
    multiplication = sum_term.arguments[1]
    assert multiplication.operator.name == "*"
    assert [argument.symbol for argument in multiplication.arguments if isinstance(argument, Constant)] == ["2", "3"]

    assert isinstance(list_term, ListTerm)
    assert list_term.items == (review, draft)
    assert isinstance(negation, CompoundTerm)
    assert negation.operator.name == "-"
    assert len(negation.arguments) == 1
    assert isinstance(negation.arguments[0], CompoundTerm)
    power = negation.arguments[0]
    assert power.operator.name == "^"
    assert isinstance(power.arguments[0], Constant)
    assert power.arguments[0].symbol == "4"
    assert isinstance(power.arguments[1], CompoundTerm)
    nested_power = power.arguments[1]
    assert nested_power.operator.name == "^"
    assert [argument.symbol for argument in nested_power.arguments if isinstance(argument, Constant)] == ["2", "3"]


def test_duplicate_declarations_are_retained_but_first_declaration_owns_lookup() -> None:
    result = parse_workflow(
        """
        const item: First;
        const item: Second;
        workflow duplicate { custom(item) == true; }
        """
    )

    assert result.diagnostics == ()
    assert isinstance(result.core_ir, WorkflowFile)
    first, second = result.core_ir.constants
    assert [first.symbol, second.symbol] == ["item", "item"]
    assert first is not second
    call = result.core_ir.workflows[0].assertions[0].lhs
    assert isinstance(call, CompoundTerm)
    assert call.arguments[0] is first


def test_syntax_errors_return_diagnostics_without_core_ir() -> None:
    result = parse_workflow("workflow broken { custom(value) = true; }")

    assert result.core_ir is None
    assert result.diagnostics
    diagnostic = result.diagnostics[0]
    assert diagnostic.severity == "error"
    assert diagnostic.message
    assert diagnostic.span is not None
    assert (diagnostic.span.start.line, diagnostic.span.start.column) == (1, 33)
    assert (diagnostic.span.end.line, diagnostic.span.end.column) == (1, 34)


def test_eof_diagnostics_have_a_visible_half_open_span() -> None:
    result = parse_workflow("workflow broken { custom(value) == true;")

    assert result.core_ir is None
    assert result.diagnostics
    span = result.diagnostics[0].span
    assert span is not None
    assert span.end.column == span.start.column + 1
