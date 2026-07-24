"""Parse FusionFlow source into target-neutral Workflow Core IR."""

from __future__ import annotations

from typing import Any, ClassVar

from antlr4 import CommonTokenStream, InputStream, Token

from .contracts import Diagnostic, ParseResult, SourcePosition, SourceSpan
from .core_ir import (
    Assertion,
    CompoundTerm,
    Concept,
    ConnectiveFormula,
    Constant,
    Formula,
    IfTerm,
    ListTerm,
    Operator,
    Term,
    Workflow,
    WorkflowFile,
)
from .generated.FusionFlowLexer import FusionFlowLexer
from .generated.FusionFlowParser import FusionFlowParser


class _DiagnosticListener:
    """Collect ANTLR errors as one-based, half-open public source spans."""

    def __init__(self) -> None:
        self.diagnostics: list[Diagnostic] = []

    def __getattr__(self, name: str) -> Any:
        if name == "syntaxError":
            return self._syntax_error
        raise AttributeError(name)

    def _syntax_error(
        self,
        recognizer: object,
        offending_symbol: object,
        line: int,
        column: int,
        message: str,
        error: object,
    ) -> None:
        del recognizer, error
        token = offending_symbol if isinstance(offending_symbol, Token) else None
        width = 1 if token is None or token.type == Token.EOF else max(len(token.text or ""), 1)
        start_column = column + 1
        self.diagnostics.append(
            Diagnostic(
                severity="error",
                message=message,
                span=SourceSpan(
                    start=SourcePosition(line=line, column=start_column),
                    end=SourcePosition(line=line, column=start_column + width),
                ),
            )
        )


class _CoreIRVisitor:
    """Lower a parse tree while reusing declarations by their source symbol.

    The traversal follows KEDispatcher's handwritten visitor pattern. Reusing
    concepts, constants, and operators preserves shared Core IR references.
    """

    _COMPARISON_OPERATORS: ClassVar[dict[str, str]] = {
        "<": "comparison_lt_op",
        "<=": "comparison_lte_op",
        ">": "comparison_gt_op",
        ">=": "comparison_gte_op",
    }

    def __init__(self) -> None:
        self._concepts: dict[str, Concept] = {}
        self._constants: dict[str, Constant] = {}
        self._boolean_constants: dict[bool, Constant] = {}
        self._operators: dict[str, Operator] = {}

    def visit_workflow_file(self, context: Any) -> WorkflowFile:
        declared_symbols = tuple(
            dict.fromkeys(self.visit_const_decl(declaration).symbol for declaration in context.constDecl())
        )
        workflows = tuple(self.visit_workflow_decl(workflow) for workflow in context.workflowDecl())
        constants = tuple(self._constants[symbol] for symbol in declared_symbols)
        return WorkflowFile(constants=constants, workflows=workflows)

    def visit_const_decl(self, context: Any) -> Constant:
        symbol = self._strip_quotes(context.constantName().getText())
        concepts = tuple(
            dict.fromkeys(
                self._resolve_concept(concept.getText()) for concept in context.conceptNameList().conceptName()
            )
        )
        existing = self._constants.get(symbol)
        if existing is not None:
            if set(existing.belong_concepts) == set(concepts):
                return existing
            raise ValueError(
                f"Conflicting FusionFlow constant declaration for {symbol!r}: "
                f"{existing.belong_concepts!r} versus {concepts!r}."
            )
        constant = Constant(symbol=symbol, belong_concepts=concepts)
        self._constants[symbol] = constant
        return constant

    def visit_workflow_decl(self, context: Any) -> Workflow:
        return Workflow(
            name=str(context.workflowName().getText()),
            assertions=tuple(self.visit_assertion(item.assertion()) for item in context.workflowItem()),
        )

    def visit_assertion(self, context: Any) -> Assertion:
        terms = context.term()
        return Assertion(lhs=self.visit_term(terms[0]), rhs=self.visit_term(terms[1]))

    def visit_formula(self, context: Any) -> Formula:
        comparison = context.comparison()
        if comparison is not None:
            return self.visit_comparison(comparison)
        if context.NOT() is not None:
            return ConnectiveFormula(formula_left=self.visit_formula(context.formula(0)), connective="NOT")
        if context.left is not None and context.right is not None:
            connective = "AND" if context.AND() is not None else "OR"
            return ConnectiveFormula(
                formula_left=self.visit_formula(context.left),
                connective=connective,
                formula_right=self.visit_formula(context.right),
            )
        return self.visit_formula(context.formula(0))

    def visit_comparison(self, context: Any) -> Formula:
        terms = context.term()
        lhs = self.visit_term(terms[0])
        rhs = self.visit_term(terms[1])
        symbol = context.comparisonOp().getText()
        equality = Assertion(lhs=lhs, rhs=rhs)
        if symbol == "=":
            return equality
        if symbol == "!=":
            # HACK: FusionFlow intentionally keeps != as NOT equality; gk uses comparison_ne_op.
            return ConnectiveFormula(formula_left=equality, connective="NOT")
        return Assertion(
            lhs=CompoundTerm(
                operator=self._resolve_operator(self._COMPARISON_OPERATORS[symbol]),
                arguments=(lhs, rhs),
            ),
            rhs=self._boolean_constant("true"),
        )

    def visit_term(self, context: Any) -> Term:
        if context.left is not None and context.right is not None:
            return CompoundTerm(
                operator=self._resolve_operator(context.op.text),
                arguments=(self.visit_term(context.left), self.visit_term(context.right)),
            )

        if context.op is not None:
            operand = self.visit_term(context.term(0))
            if context.op.text == "+":
                return operand
            return CompoundTerm(operator=self._resolve_operator("-"), arguments=(operand,))

        conditional = context.ifExpression()
        if conditional is not None:
            return self.visit_if_expression(conditional)

        operator_name = context.operatorName()
        if operator_name is not None:
            term_list = context.termList()
            arguments = () if term_list is None else tuple(self.visit_term(term) for term in term_list.term())
            return CompoundTerm(
                operator=self._resolve_operator(operator_name.getText()),
                arguments=arguments,
            )

        list_literal = context.listLiteral()
        if list_literal is not None:
            return self.visit_list_literal(list_literal)

        atomic_term = context.atomicTerm()
        if atomic_term is not None:
            return self.visit_atomic_term(atomic_term)

        return self.visit_term(context.term(0))

    def visit_if_expression(self, context: Any) -> IfTerm:
        branches = context.term()
        return IfTerm(
            condition=self.visit_formula(context.formula()),
            when_true=self.visit_term(branches[0]),
            when_false=self.visit_term(branches[1]),
        )

    def visit_list_literal(self, context: Any) -> ListTerm:
        term_list = context.termList()
        items = () if term_list is None else tuple(self.visit_term(term) for term in term_list.term())
        return ListTerm(items=items)

    def visit_atomic_term(self, context: Any) -> Constant:
        boolean_literal = context.booleanLiteral()
        if boolean_literal is not None:
            return self._boolean_constant(boolean_literal.getText())
        return self._resolve_constant(context.constantName().getText())

    def _resolve_constant(self, raw_text: str) -> Constant:
        is_numeric = raw_text.replace(".", "", 1).isdigit()
        if is_numeric:
            value = float(raw_text) if "." in raw_text else int(raw_text)
            return Constant(symbol=str(value), belong_concepts=(self._resolve_concept("ComplexNumber"),))

        symbol = self._strip_quotes(raw_text)
        existing = self._constants.get(symbol)
        if existing is not None:
            return existing

        constant = Constant(symbol=symbol, belong_concepts=(self._resolve_concept("Any"),))
        self._constants[symbol] = constant
        return constant

    def _boolean_constant(self, raw_text: str) -> Constant:
        value = raw_text.lower() == "true"
        constant = self._boolean_constants.get(value)
        if constant is None:
            constant = Constant(symbol=str(value), belong_concepts=(self._resolve_concept("Bool"),))
            self._boolean_constants[value] = constant
        return constant

    def _resolve_concept(self, name: str) -> Concept:
        concept = self._concepts.get(name)
        if concept is None:
            concept = Concept(name=name)
            self._concepts[name] = concept
        return concept

    def _resolve_operator(self, name: str) -> Operator:
        operator = self._operators.get(name)
        if operator is None:
            operator = Operator(name=name)
            self._operators[name] = operator
        return operator

    @staticmethod
    def _strip_quotes(symbol: str) -> str:
        if symbol.startswith('"') and symbol.endswith('"'):
            return symbol[1:-1]
        return symbol


def parse_workflow(source: str) -> ParseResult:
    """Parse syntax and lower it without performing static workflow checks.

    Syntax failures are returned as parser diagnostics. Formula equality lowers
    to an assertion, inequality to NOT over an assertion, and ordered
    comparisons to KEDispatcher comparison operators asserted true. Compilation
    and workflow execution are outside this boundary.
    """

    listener = _DiagnosticListener()
    lexer = FusionFlowLexer(InputStream(source))
    lexer.removeErrorListeners()
    lexer.addErrorListener(listener)

    parser = FusionFlowParser(CommonTokenStream(lexer))
    parser.removeErrorListeners()
    parser.addErrorListener(listener)
    tree = parser.workflowFile()

    diagnostics = tuple(listener.diagnostics)
    if diagnostics:
        return ParseResult(core_ir=None, diagnostics=diagnostics)
    return ParseResult(core_ir=_CoreIRVisitor().visit_workflow_file(tree), diagnostics=diagnostics)
