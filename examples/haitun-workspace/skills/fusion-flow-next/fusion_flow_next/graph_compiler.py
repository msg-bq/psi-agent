"""Compile FusionFlow Core IR into the psi-agent workflow graph model."""

from __future__ import annotations

from dataclasses import dataclass

from psi_agent.workflow_graph.model import (
    ArtifactNode,
    ConsumesEdge,
    ForeachEdge,
    ProducesEdge,
    ResourceRequirement,
    StepNode,
    WorkflowGraph,
    WorkflowGraphError,
    WorkflowPolicy,
)

from .compiler import CoreIRCompiler, _CompiledDeclarations
from .core_ir import Assertion, CompoundTerm, Constant, IfTerm, ListTerm, Workflow


class WorkflowGraphCompilationError(ValueError):
    """A Core IR workflow cannot be represented by the graph target."""


@dataclass(frozen=True, slots=True)
class WorkflowGraphCompilation:
    """One compiled graph and the assertions outside this target's vocabulary."""

    graph: WorkflowGraph
    residual_assertions: tuple[Assertion, ...]


@dataclass(frozen=True, slots=True)
class _CompiledCall:
    operator_name: str
    arguments: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class _CompiledList:
    items: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class _CompiledAssertion:
    source: Assertion
    call: _CompiledCall | None = None
    rhs: object | None = None


class WorkflowGraphCompiler(CoreIRCompiler):
    """Concrete Core IR compiler for cyclic Step-Artifact workflow graphs."""

    _GRAPH_OPERATORS = frozenset(
        {
            "consumes",
            "consumes_multi",
            "foreach_item",
            "input_workflow",
            "input_workflow_multi",
            "max_attempts",
            "max_concurrency",
            "output_workflow",
            "output_workflow_multi",
            "produces",
            "produces_multi",
            "resource_requirement",
            "step_executor",
            "step_instruction",
            "step_name",
            "step_timeout",
            "workflow_timeout",
        }
    )
    _EXECUTOR_CONCEPTS = frozenset({"Human", "Agent", "Program"})

    def _compile_constant(self, constant: Constant) -> object:
        return constant

    def _compile_compound_term(self, term: CompoundTerm) -> object:
        return _CompiledCall(
            operator_name=term.operator.name,
            arguments=tuple(self._compile_term(argument) for argument in term.arguments),
        )

    def _compile_list_term(self, term: ListTerm) -> object:
        return _CompiledList(items=tuple(self._compile_term(item) for item in term.items))

    def _compile_if_term(self, term: IfTerm) -> object:
        try:
            return super()._compile_if_term(term)
        except ValueError as error:
            raise WorkflowGraphCompilationError(str(error)) from error

    def _compile_assertion(self, assertion: Assertion) -> object:
        if not isinstance(assertion.lhs, CompoundTerm):
            return _CompiledAssertion(source=assertion)
        if assertion.lhs.operator.name not in self._GRAPH_OPERATORS:
            return _CompiledAssertion(source=assertion)
        call = self._compile_term(assertion.lhs)
        if not isinstance(call, _CompiledCall):
            raise TypeError("compound term hook returned an invalid graph call")
        return _CompiledAssertion(
            source=assertion,
            call=call,
            rhs=self._compile_term(assertion.rhs),
        )

    def _build_workflow(
        self,
        workflow: Workflow,
        *,
        assertions: tuple[object, ...],
    ) -> object:
        step_ids: set[str] = set()
        artifact_ids: set[str] = set()
        input_ids: set[str] = set()
        output_ids: set[str] = set()
        step_names: dict[str, str] = {}
        step_instructions: dict[str, str] = {}
        step_executors: dict[str, str] = {}
        step_timeouts: dict[str, int] = {}
        step_attempts: dict[str, int] = {}
        resources: dict[tuple[str, str], int] = {}
        consumes: set[tuple[str, str]] = set()
        produces: set[tuple[str, str]] = set()
        foreach_by_step: dict[str, tuple[str, str]] = {}
        binding_owners: dict[str, str] = {}
        max_concurrency: int | None = None
        workflow_timeout: int | None = None
        residual: list[Assertion] = []

        for compiled in assertions:
            if not isinstance(compiled, _CompiledAssertion):
                raise TypeError("workflow graph compiler received an invalid compiled assertion")
            if compiled.call is None:
                residual.append(compiled.source)
                continue

            operator_name = compiled.call.operator_name
            arguments = compiled.call.arguments
            rhs = compiled.rhs

            if operator_name in {
                "input_workflow_multi",
                "output_workflow_multi",
                "consumes_multi",
                "produces_multi",
            }:
                self._require_arity(arguments, 1, operator_name)
                item_ids = self._list_symbols(rhs, operator_name)
                owner_id = self._symbol(arguments[0], f"{operator_name} owner")
                if operator_name in {"input_workflow_multi", "output_workflow_multi"}:
                    self._require_owner(owner_id, workflow.name, operator_name)
                    target = input_ids if operator_name == "input_workflow_multi" else output_ids
                    for artifact_id in item_ids:
                        self._add_unique(target, artifact_id, operator_name)
                        artifact_ids.add(artifact_id)
                    continue

                step_ids.add(owner_id)
                for artifact_id in item_ids:
                    if operator_name == "consumes_multi":
                        self._add_unique(consumes, (artifact_id, owner_id), operator_name)
                    else:
                        self._add_unique(produces, (owner_id, artifact_id), operator_name)
                    artifact_ids.add(artifact_id)
                continue

            if operator_name in {"input_workflow", "output_workflow"}:
                self._require_arity(arguments, 2, operator_name)
                owner_id = self._symbol(arguments[0], f"{operator_name} owner")
                self._require_owner(owner_id, workflow.name, operator_name)
                artifact_id = self._symbol(arguments[1], f"{operator_name} artifact")
                self._require_true(rhs, operator_name)
                target = input_ids if operator_name == "input_workflow" else output_ids
                self._add_unique(target, artifact_id, operator_name)
                artifact_ids.add(artifact_id)
                continue

            if operator_name in {"max_concurrency", "workflow_timeout"}:
                self._require_arity(arguments, 1, operator_name)
                owner_id = self._symbol(arguments[0], f"{operator_name} owner")
                self._require_owner(owner_id, workflow.name, operator_name)
                value = self._positive_integer(rhs, operator_name)
                if operator_name == "max_concurrency":
                    if max_concurrency is not None:
                        raise WorkflowGraphCompilationError("duplicate max_concurrency")
                    max_concurrency = value
                else:
                    if workflow_timeout is not None:
                        raise WorkflowGraphCompilationError("duplicate workflow_timeout")
                    workflow_timeout = value
                continue

            if operator_name in {"step_name", "step_instruction", "step_executor", "step_timeout", "max_attempts"}:
                self._require_arity(arguments, 1, operator_name)
            else:
                self._require_arity(arguments, 2, operator_name)
            step_id = self._symbol(arguments[0], f"{operator_name} step")
            step_ids.add(step_id)

            if operator_name == "step_name":
                self._set_once(step_names, step_id, self._symbol(rhs, "step_name value"), operator_name)
            elif operator_name == "step_instruction":
                self._set_once(
                    step_instructions,
                    step_id,
                    self._symbol(rhs, "step_instruction value"),
                    operator_name,
                )
            elif operator_name == "step_executor":
                executor = self._constant(rhs, "step_executor value")
                self._validate_executor_concepts(executor)
                self._set_once(step_executors, step_id, executor.symbol, operator_name)
            elif operator_name == "consumes":
                artifact_id = self._symbol(arguments[1], "consumed artifact")
                self._require_true(rhs, operator_name)
                self._add_unique(consumes, (artifact_id, step_id), operator_name)
                artifact_ids.add(artifact_id)
            elif operator_name == "produces":
                artifact_id = self._symbol(arguments[1], "produced artifact")
                self._require_true(rhs, operator_name)
                self._add_unique(produces, (step_id, artifact_id), operator_name)
                artifact_ids.add(artifact_id)
            elif operator_name == "foreach_item":
                source_id = self._symbol(arguments[1], "foreach source")
                binding_id = self._symbol(rhs, "foreach item binding")
                if step_id in foreach_by_step:
                    raise WorkflowGraphCompilationError(f"duplicate foreach_item for step {step_id!r}")
                if binding_id in binding_owners:
                    raise WorkflowGraphCompilationError(f"duplicate foreach item binding {binding_id!r}")
                foreach_by_step[step_id] = (source_id, binding_id)
                binding_owners[binding_id] = step_id
                artifact_ids.update((source_id, binding_id))
            elif operator_name == "step_timeout":
                self._set_once(
                    step_timeouts,
                    step_id,
                    self._positive_integer(rhs, operator_name),
                    operator_name,
                )
            elif operator_name == "max_attempts":
                self._set_once(
                    step_attempts,
                    step_id,
                    self._positive_integer(rhs, operator_name),
                    operator_name,
                )
            else:
                resource_id = self._symbol(arguments[1], "resource identity")
                self._set_once(
                    resources,
                    (step_id, resource_id),
                    self._positive_integer(rhs, operator_name),
                    operator_name,
                )

        for step_id in sorted(step_ids):
            if step_id not in step_names:
                raise WorkflowGraphCompilationError(f"step {step_id!r} has no step_name")
            if step_id not in step_executors:
                raise WorkflowGraphCompilationError(f"step {step_id!r} has no step_executor")

        try:
            graph = WorkflowGraph(
                workflow_id=workflow.name,
                steps=tuple(
                    StepNode(
                        step_id=step_id,
                        name_id=step_names[step_id],
                        executor_id=step_executors[step_id],
                        instruction_id=step_instructions.get(step_id),
                        timeout_seconds=step_timeouts.get(step_id),
                        max_attempts=step_attempts.get(step_id, 1),
                        resources=tuple(
                            ResourceRequirement(resource_id=resource_id, amount=amount)
                            for (owner_id, resource_id), amount in sorted(resources.items())
                            if owner_id == step_id
                        ),
                    )
                    for step_id in sorted(step_ids)
                ),
                artifacts=tuple(
                    ArtifactNode(
                        artifact_id=artifact_id,
                        is_input=artifact_id in input_ids,
                        is_output=artifact_id in output_ids,
                        binding_step_id=binding_owners.get(artifact_id),
                    )
                    for artifact_id in sorted(artifact_ids)
                ),
                edges=(
                    tuple(
                        ConsumesEdge(artifact_id=artifact_id, step_id=step_id)
                        for artifact_id, step_id in sorted(consumes)
                    )
                    + tuple(
                        ForeachEdge(
                            artifact_id=source_id,
                            step_id=step_id,
                            item_binding_id=binding_id,
                        )
                        for step_id, (source_id, binding_id) in sorted(foreach_by_step.items())
                    )
                    + tuple(
                        ProducesEdge(step_id=step_id, artifact_id=artifact_id)
                        for step_id, artifact_id in sorted(produces)
                    )
                ),
                policy=WorkflowPolicy(
                    max_concurrency=max_concurrency,
                    timeout_seconds=workflow_timeout,
                ),
            )
        except WorkflowGraphError as error:
            raise WorkflowGraphCompilationError(str(error)) from error

        return WorkflowGraphCompilation(
            graph=graph,
            residual_assertions=tuple(residual),
        )

    def _build_program(
        self,
        declarations: _CompiledDeclarations,
        *,
        workflows: tuple[object, ...],
    ) -> object:
        del declarations
        return workflows

    @staticmethod
    def _require_arity(arguments: tuple[object, ...], expected: int, operator_name: str) -> None:
        if len(arguments) != expected:
            raise WorkflowGraphCompilationError(f"{operator_name} expects {expected} arguments, got {len(arguments)}")

    @staticmethod
    def _constant(value: object, context: str) -> Constant:
        if not isinstance(value, Constant) or not value.symbol:
            raise WorkflowGraphCompilationError(f"{context} must be a non-empty constant")
        return value

    @classmethod
    def _symbol(cls, value: object, context: str) -> str:
        return cls._constant(value, context).symbol

    @classmethod
    def _list_symbols(cls, value: object, operator_name: str) -> tuple[str, ...]:
        if not isinstance(value, _CompiledList):
            raise WorkflowGraphCompilationError(f"{operator_name} RHS must be a List term")
        symbols: list[str] = []
        seen: set[str] = set()
        for item in value.items:
            symbol = cls._symbol(item, f"{operator_name} list item")
            if symbol in seen:
                raise WorkflowGraphCompilationError(f"duplicate {operator_name} list item: {symbol!r}")
            seen.add(symbol)
            symbols.append(symbol)
        return tuple(symbols)

    @staticmethod
    def _require_owner(owner_id: str, workflow_id: str, operator_name: str) -> None:
        if owner_id != workflow_id:
            raise WorkflowGraphCompilationError(
                f"{operator_name} owner {owner_id!r} does not match workflow {workflow_id!r}"
            )

    @classmethod
    def _require_true(cls, value: object, operator_name: str) -> None:
        if cls._symbol(value, f"{operator_name} RHS") != "True":
            raise WorkflowGraphCompilationError(f"{operator_name} RHS must be the True constant")

    @classmethod
    def _positive_integer(cls, value: object, operator_name: str) -> int:
        symbol = cls._symbol(value, f"{operator_name} RHS")
        if not symbol.isascii() or not symbol.isdecimal():
            raise WorkflowGraphCompilationError(f"{operator_name} RHS must be a positive integer constant")
        try:
            number = int(symbol)
        except ValueError as error:
            raise WorkflowGraphCompilationError(f"{operator_name} RHS must be a positive integer constant") from error
        if number < 1:
            raise WorkflowGraphCompilationError(f"{operator_name} RHS must be a positive integer constant")
        return number

    @classmethod
    def _validate_executor_concepts(cls, executor: Constant) -> None:
        if not executor.belong_concepts:
            return
        matches = {concept.name for concept in executor.belong_concepts} & cls._EXECUTOR_CONCEPTS
        if len(matches) != 1:
            raise WorkflowGraphCompilationError("step_executor must belong to exactly one of Human, Agent, or Program")

    @staticmethod
    def _add_unique[T](values: set[T], value: T, operator_name: str) -> None:
        if value in values:
            raise WorkflowGraphCompilationError(f"duplicate {operator_name}: {value!r}")
        values.add(value)

    @staticmethod
    def _set_once[K, V](
        values: dict[K, V],
        key: K,
        value: V,
        operator_name: str,
    ) -> None:
        if key in values:
            raise WorkflowGraphCompilationError(f"duplicate {operator_name}: {key!r}")
        values[key] = value
