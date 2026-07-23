"""Shared compiler flow for backends that use the FusionFlow Core IR shape."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import NoReturn

from .core_ir import (
    Assertion,
    CompoundTerm,
    ConnectiveFormula,
    Constant,
    IfTerm,
    ListTerm,
    Workflow,
    WorkflowFile,
)


@dataclass(frozen=True, slots=True)
class _CompiledDeclarations:
    constants: Mapping[Constant, object]


class CoreIRCompiler:
    """Compile FusionFlow Core IR through backend-specific node hooks."""

    def compile(self, core_ir: WorkflowFile) -> object:
        """Compile a workflow file without storing the input on the compiler."""

        constants = tuple(dict.fromkeys(core_ir.constants))
        declarations = _CompiledDeclarations(
            constants={constant: self._compile_constant(constant) for constant in constants},
        )
        return self._build_program(
            declarations,
            workflows=tuple(self._compile_workflow(workflow) for workflow in core_ir.workflows),
        )

    def _compile_workflow(self, workflow: Workflow) -> object:
        return self._build_workflow(
            workflow,
            assertions=tuple(self._compile_formula(assertion) for assertion in workflow.assertions),
        )

    def _compile_formula(self, formula: object) -> object:
        if isinstance(formula, Assertion):
            return self._compile_assertion(formula)
        if isinstance(formula, ConnectiveFormula):
            return self._compile_connective_formula(formula)
        return self._unsupported("formula", formula)

    def _compile_term(self, term: object) -> object:
        if isinstance(term, Constant):
            return self._compile_constant(term)
        if isinstance(term, CompoundTerm):
            return self._compile_compound_term(term)
        if isinstance(term, ListTerm):
            return self._compile_list_term(term)
        if isinstance(term, IfTerm):
            return self._compile_if_term(term)
        return self._unsupported("term", term)

    def _compile_constant(self, constant: Constant) -> object:
        return self._unsupported("constant declaration", constant)

    def _compile_compound_term(self, term: CompoundTerm) -> object:
        return self._unsupported("compound term", term)

    def _compile_list_term(self, term: ListTerm) -> object:
        return self._unsupported("list term", term)

    def _compile_if_term(self, term: IfTerm) -> object:
        return self._unsupported("if term", term)

    def _compile_assertion(self, assertion: Assertion) -> object:
        return self._unsupported("assertion", assertion)

    def _compile_connective_formula(self, formula: ConnectiveFormula) -> object:
        return self._unsupported("connective formula", formula)

    def _build_workflow(
        self,
        workflow: Workflow,
        *,
        assertions: tuple[object, ...],
    ) -> object:
        del workflow, assertions
        raise NotImplementedError(f"{type(self).__name__} must implement _build_workflow().")

    def _build_program(
        self,
        declarations: _CompiledDeclarations,
        *,
        workflows: tuple[object, ...],
    ) -> object:
        del declarations, workflows
        raise NotImplementedError(f"{type(self).__name__} must implement _build_program().")

    def _unsupported(self, label: str, node: object) -> NoReturn:
        raise ValueError(
            f"{type(self).__name__} cannot compile unsupported {label} node of type {type(node).__name__}."
        )
