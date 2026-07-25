"""Lower checked FusionFlow Core IR into the psi-agent workflow graph model.

The shared :class:`CoreIRCompiler` owns traversal.  This module only implements
the target-specific hooks: it classifies graph assertions, collects their
facts, and finally builds the immutable Step-Artifact graph.
"""

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
    """A checked Core IR workflow cannot be represented by the graph target."""


@dataclass(frozen=True, slots=True)
class WorkflowGraphCompilation:
    """One graph plus the assertions deliberately left for another backend."""

    graph: WorkflowGraph
    residual_assertions: tuple[Assertion, ...]


@dataclass(frozen=True, slots=True)
class _CompiledCall:
    """A compound Core IR term reduced to the data needed for op dispatch."""

    operator_name: str
    arguments: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class _CompiledList:
    """A compiled ``ListTerm`` kept distinct from a call's argument tuple."""

    items: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class _CompiledAssertion:
    """An assertion classified for graph lowering.

    ``call is None`` means that the assertion does not use the graph
    vocabulary.  Its untouched ``source`` is then returned as residual IR.
    """

    source: Assertion
    call: _CompiledCall | None = None
    rhs: object | None = None


class WorkflowGraphCompiler(CoreIRCompiler):
    """Compile graph operators while preserving unrelated assertions.

    Graph operators fall into four groups:

    * workflow boundaries: ``input_workflow*`` and ``output_workflow*``;
    * step metadata: ``step_name``, ``step_instruction``, and ``step_executor``;
    * dataflow: ``consumes*``, ``produces*``, and ``foreach_item``;
    * policies: timeouts, retries, resources, and concurrency.

    The compiler only overrides protected hooks.  Public traversal and
    unsupported-node handling remain owned by :class:`CoreIRCompiler`.
    """

    _GRAPH_OPERATORS = frozenset(
        {
            # Workflow boundary operators.
            "input_workflow",
            "input_workflow_multi",
            "output_workflow",
            "output_workflow_multi",
            # Required and optional step metadata.
            "step_name",
            "step_instruction",
            "step_executor",
            # Step-to-artifact dataflow operators.
            "consumes",
            "consumes_multi",
            "produces",
            "produces_multi",
            "foreach_item",
            # Step and workflow policies.
            "step_timeout",
            "max_attempts",
            "resource_requirement",
            "max_concurrency",
            "workflow_timeout",
        }
    )
    # Executor concepts are mutually exclusive in the graph target.
    _EXECUTOR_CONCEPTS = frozenset({"Human", "Agent", "Program"})

    def _compile_constant(self, constant: Constant) -> object:
        """Preserve both the constant symbol and its executor concept tags."""

        return constant

    def _compile_compound_term(self, term: CompoundTerm) -> object:
        """Compile an operator application without interpreting the operator yet.

        Interpretation belongs to ``_build_workflow``, where the workflow name
        and the other assertions are available for cross-assertion validation.
        """

        return _CompiledCall(
            operator_name=term.operator.name,
            arguments=tuple(self._compile_term(argument) for argument in term.arguments),
        )

    def _compile_list_term(self, term: ListTerm) -> object:
        """Compile every list item while retaining the Core IR list boundary."""

        return _CompiledList(items=tuple(self._compile_term(item) for item in term.items))

    def _compile_if_term(self, term: IfTerm) -> object:
        """Reject conditional graph values and expose a graph-specific error.

        The base hook fails closed.  Wrapping its error keeps callers from
        depending on the generic compiler's exception type.
        """

        try:
            return super()._compile_if_term(term)
        except ValueError as error:
            raise WorkflowGraphCompilationError(str(error)) from error

    def _compile_assertion(self, assertion: Assertion) -> object:
        """Classify one equality as a graph assertion or residual Core IR.

        A recognized graph call may occur on either side because ``Assertion``
        models equality, not assignment.  Unknown operators stay completely
        untouched: notably, their children are not traversed and therefore
        cannot fail graph compilation.
        """

        # Inspect both top-level terms symmetrically.  Nested graph calls inside
        # an unknown outer operator still belong to that operator's backend.
        lhs_is_graph_call = (
            isinstance(assertion.lhs, CompoundTerm) and assertion.lhs.operator.name in self._GRAPH_OPERATORS
        )
        rhs_is_graph_call = (
            isinstance(assertion.rhs, CompoundTerm) and assertion.rhs.operator.name in self._GRAPH_OPERATORS
        )

        # An equality with no graph call must survive as exact residual IR.
        if not lhs_is_graph_call and not rhs_is_graph_call:
            return _CompiledAssertion(source=assertion)

        # Two graph calls do not have a call/value orientation and cannot map to
        # one graph fact without inventing target semantics.
        if lhs_is_graph_call and rhs_is_graph_call:
            raise WorkflowGraphCompilationError("graph assertion cannot contain graph operators on both sides")

        # Normalize equality direction before entering the existing lowering
        # path: graph_call = value and value = graph_call are equivalent.
        call_term, value_term = (assertion.lhs, assertion.rhs) if lhs_is_graph_call else (assertion.rhs, assertion.lhs)

        # Recognized operators are compiled recursively and fail closed on an
        # unsupported child such as IfTerm.
        call = self._compile_term(call_term)
        if not isinstance(call, _CompiledCall):
            raise TypeError("compound term hook returned an invalid graph call")
        return _CompiledAssertion(
            source=assertion,
            call=call,
            rhs=self._compile_term(value_term),
        )

    def _build_workflow(
        self,
        workflow: Workflow,
        *,
        assertions: tuple[object, ...],
    ) -> object:
        """Collect graph facts, validate cross-op invariants, and build one graph.

        The first pass records identity, metadata, edges, and policies in
        duplicate-detecting containers.  Construction is deferred until every
        assertion has been seen because graph validity depends on facts spread
        across multiple operators.
        """

        # Identities are discovered from any operator, not from declarations.
        step_ids: set[str] = set()
        artifact_ids: set[str] = set()
        input_ids: set[str] = set()
        output_ids: set[str] = set()

        # Step metadata is keyed by step so each scalar property can occur once.
        step_names: dict[str, str] = {}
        step_instructions: dict[str, str] = {}
        step_executors: dict[str, str] = {}
        step_timeouts: dict[str, int] = {}
        step_attempts: dict[str, int] = {}

        # Edges and resources use composite keys to reject exact duplicates.
        resources: dict[tuple[str, str], int] = {}
        consumes: set[tuple[str, str]] = set()
        produces: set[tuple[str, str]] = set()

        # A foreach step has one source and creates one step-local item binding.
        foreach_by_step: dict[str, tuple[str, str]] = {}
        binding_owners: dict[str, str] = {}

        # Workflow-wide policies are optional but singular.
        max_concurrency: int | None = None
        workflow_timeout: int | None = None

        # Assertions outside the graph vocabulary remain available to callers.
        residual: list[Assertion] = []

        for compiled in assertions:
            # CoreIRCompiler must feed this backend only values returned by
            # _compile_assertion; a different value signals a broken hook contract.
            if not isinstance(compiled, _CompiledAssertion):
                raise TypeError("workflow graph compiler received an invalid compiled assertion")

            # Unknown/non-compound assertions are intentionally not interpreted.
            if compiled.call is None:
                residual.append(compiled.source)
                continue

            # All recognized graph assertions have the normalized shape
            # operator(arguments...) = rhs.
            operator_name = compiled.call.operator_name
            arguments = compiled.call.arguments
            rhs = compiled.rhs

            # Multi operators encode their artifact collection as one RHS List:
            #   input_workflow_multi(workflow) = List(...)
            #   consumes_multi(step) = List(...)
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
                    # Workflow boundary lists must name the workflow being built.
                    self._require_owner(owner_id, workflow.name, operator_name)
                    target = input_ids if operator_name == "input_workflow_multi" else output_ids
                    for artifact_id in item_ids:
                        self._add_unique(target, artifact_id, operator_name)
                        artifact_ids.add(artifact_id)
                    continue

                # Step multi-edge operators discover the step and expand each
                # list item into one ordinary graph edge.
                step_ids.add(owner_id)
                for artifact_id in item_ids:
                    if operator_name == "consumes_multi":
                        # Core IR: consumes_multi(step) = List(artifacts)
                        # Graph:   artifact --consumes--> step
                        self._add_unique(consumes, (artifact_id, owner_id), operator_name)
                    else:
                        # Core IR: produces_multi(step) = List(artifacts)
                        # Graph:   step --produces--> artifact
                        self._add_unique(produces, (owner_id, artifact_id), operator_name)
                    artifact_ids.add(artifact_id)
                continue

            # Scalar boundary assertions use an explicit True RHS:
            #   input_workflow(workflow, artifact) = True
            #   output_workflow(workflow, artifact) = True
            if operator_name in {"input_workflow", "output_workflow"}:
                self._require_arity(arguments, 2, operator_name)
                owner_id = self._symbol(arguments[0], f"{operator_name} owner")
                self._require_owner(owner_id, workflow.name, operator_name)
                artifact_id = self._symbol(arguments[1], f"{operator_name} artifact")
                self._require_true(rhs, operator_name)
                target = input_ids if operator_name == "input_workflow" else output_ids
                self._add_unique(target, artifact_id, operator_name)
                # Boundary-only artifacts still need a graph node.
                artifact_ids.add(artifact_id)
                continue

            # Workflow policies are positive integer properties of this workflow:
            #   max_concurrency(workflow) = count
            #   workflow_timeout(workflow) = seconds
            if operator_name in {"max_concurrency", "workflow_timeout"}:
                self._require_arity(arguments, 1, operator_name)
                owner_id = self._symbol(arguments[0], f"{operator_name} owner")
                self._require_owner(owner_id, workflow.name, operator_name)
                value = self._positive_integer(rhs, operator_name)
                if operator_name == "max_concurrency":
                    # None distinguishes "not supplied" from a duplicate value.
                    if max_concurrency is not None:
                        raise WorkflowGraphCompilationError("duplicate max_concurrency")
                    max_concurrency = value
                else:
                    if workflow_timeout is not None:
                        raise WorkflowGraphCompilationError("duplicate workflow_timeout")
                    workflow_timeout = value
                continue

            # The remaining vocabulary is step-scoped.  Metadata/policy
            # operators are unary; edge/resource operators take a second ID.
            if operator_name in {"step_name", "step_instruction", "step_executor", "step_timeout", "max_attempts"}:
                self._require_arity(arguments, 1, operator_name)
            else:
                self._require_arity(arguments, 2, operator_name)
            step_id = self._symbol(arguments[0], f"{operator_name} step")
            # A step may first appear in any one of its assertions.
            step_ids.add(step_id)

            if operator_name == "step_name":
                # step_name(step) = display_name
                self._set_once(step_names, step_id, self._symbol(rhs, "step_name value"), operator_name)
            elif operator_name == "step_instruction":
                # step_instruction(step) = instruction_identity
                self._set_once(
                    step_instructions,
                    step_id,
                    self._symbol(rhs, "step_instruction value"),
                    operator_name,
                )
            elif operator_name == "step_executor":
                # step_executor(step) = executor_identity
                # Concept tags, when present, also select exactly one executor kind.
                executor = self._constant(rhs, "step_executor value")
                self._validate_executor_concepts(executor)
                self._set_once(step_executors, step_id, executor.symbol, operator_name)
            elif operator_name == "consumes":
                # consumes(step, artifact) = True
                artifact_id = self._symbol(arguments[1], "consumed artifact")
                self._require_true(rhs, operator_name)
                self._add_unique(consumes, (artifact_id, step_id), operator_name)
                artifact_ids.add(artifact_id)
            elif operator_name == "produces":
                # produces(step, artifact) = True
                artifact_id = self._symbol(arguments[1], "produced artifact")
                self._require_true(rhs, operator_name)
                self._add_unique(produces, (step_id, artifact_id), operator_name)
                artifact_ids.add(artifact_id)
            elif operator_name == "foreach_item":
                # foreach_item(step, collection_artifact) = item_binding
                # The binding is a local artifact owned by exactly this step.
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
                # step_timeout(step) = seconds
                self._set_once(
                    step_timeouts,
                    step_id,
                    self._positive_integer(rhs, operator_name),
                    operator_name,
                )
            elif operator_name == "max_attempts":
                # max_attempts(step) = count
                self._set_once(
                    step_attempts,
                    step_id,
                    self._positive_integer(rhs, operator_name),
                    operator_name,
                )
            else:
                # The only remaining graph operator is:
                #   resource_requirement(step, resource) = positive_amount
                resource_id = self._symbol(arguments[1], "resource identity")
                self._set_once(
                    resources,
                    (step_id, resource_id),
                    self._positive_integer(rhs, operator_name),
                    operator_name,
                )

        # Name and executor are the two required StepNode fields not derivable
        # from identity.  Check them after collecting every assertion so source
        # ordering never affects acceptance.
        for step_id in sorted(step_ids):
            if step_id not in step_names:
                raise WorkflowGraphCompilationError(f"step {step_id!r} has no step_name")
            if step_id not in step_executors:
                raise WorkflowGraphCompilationError(f"step {step_id!r} has no step_executor")

        try:
            # Sort every identity-derived collection for deterministic graph
            # equality and serialization independent of assertion order.
            graph = WorkflowGraph(
                workflow_id=workflow.name,
                steps=tuple(
                    StepNode(
                        step_id=step_id,
                        name_id=step_names[step_id],
                        executor_id=step_executors[step_id],
                        instruction_id=step_instructions.get(step_id),
                        timeout_seconds=step_timeouts.get(step_id),
                        # The graph model defaults retries to one when the DSL
                        # omits max_attempts.
                        max_attempts=step_attempts.get(step_id, 1),
                        resources=tuple(
                            # Resource facts are stored globally while parsing;
                            # attach only those owned by the current step.
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
                        # One artifact may be both a workflow input and output.
                        is_input=artifact_id in input_ids,
                        is_output=artifact_id in output_ids,
                        # Only foreach item bindings have a local owner.
                        binding_step_id=binding_owners.get(artifact_id),
                    )
                    for artifact_id in sorted(artifact_ids)
                ),
                edges=(
                    # Keep edge kinds in a stable consumes/foreach/produces order.
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
            # Present target-model invariant failures through the compiler's
            # public error type while preserving the original cause.
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
        """Return one compilation result per workflow in source order.

        Global constants have already served as term values; the graph target
        has no declaration table of its own.
        """

        del declarations
        return workflows

    @staticmethod
    def _require_arity(arguments: tuple[object, ...], expected: int, operator_name: str) -> None:
        """Require the exact arity defined by one graph operator."""

        if len(arguments) != expected:
            raise WorkflowGraphCompilationError(f"{operator_name} expects {expected} arguments, got {len(arguments)}")

    @staticmethod
    def _constant(value: object, context: str) -> Constant:
        """Narrow a compiled value to a non-empty Core IR constant."""

        if not isinstance(value, Constant) or not value.symbol:
            raise WorkflowGraphCompilationError(f"{context} must be a non-empty constant")
        return value

    @classmethod
    def _symbol(cls, value: object, context: str) -> str:
        """Extract the identity/literal text carried by a compiled constant."""

        return cls._constant(value, context).symbol

    @classmethod
    def _list_symbols(cls, value: object, operator_name: str) -> tuple[str, ...]:
        """Extract a duplicate-free ordered symbol list from a compiled ListTerm."""

        if not isinstance(value, _CompiledList):
            raise WorkflowGraphCompilationError(f"{operator_name} RHS must be a List term")
        symbols: list[str] = []
        seen: set[str] = set()
        for item in value.items:
            symbol = cls._symbol(item, f"{operator_name} list item")
            # Reject duplicates here because a set conversion would silently
            # erase an invalid repeated edge/boundary declaration.
            if symbol in seen:
                raise WorkflowGraphCompilationError(f"duplicate {operator_name} list item: {symbol!r}")
            seen.add(symbol)
            symbols.append(symbol)
        return tuple(symbols)

    @staticmethod
    def _require_owner(owner_id: str, workflow_id: str, operator_name: str) -> None:
        """Ensure a workflow-scoped assertion cannot mutate another workflow."""

        if owner_id != workflow_id:
            raise WorkflowGraphCompilationError(
                f"{operator_name} owner {owner_id!r} does not match workflow {workflow_id!r}"
            )

    @classmethod
    def _require_true(cls, value: object, operator_name: str) -> None:
        """Require the canonical ``True`` RHS used by boolean relation ops."""

        if cls._symbol(value, f"{operator_name} RHS") != "True":
            raise WorkflowGraphCompilationError(f"{operator_name} RHS must be the True constant")

    @classmethod
    def _positive_integer(cls, value: object, operator_name: str) -> int:
        """Parse a positive ASCII-decimal policy value without accepting signs."""

        symbol = cls._symbol(value, f"{operator_name} RHS")
        # ``str.isdecimal`` accepts non-ASCII digits; the DSL contract does not.
        if not symbol.isascii() or not symbol.isdecimal():
            raise WorkflowGraphCompilationError(f"{operator_name} RHS must be a positive integer constant")
        try:
            # Python may reject extremely long decimal strings under its
            # integer-conversion safety limit; normalize that to our API error.
            number = int(symbol)
        except ValueError as error:
            raise WorkflowGraphCompilationError(f"{operator_name} RHS must be a positive integer constant") from error
        if number < 1:
            raise WorkflowGraphCompilationError(f"{operator_name} RHS must be a positive integer constant")
        return number

    @classmethod
    def _validate_executor_concepts(cls, executor: Constant) -> None:
        """Validate optional executor typing against the graph's three kinds.

        Untyped constants remain valid for compatibility with minimal Core IR.
        A typed executor must carry exactly one recognized executor concept.
        """

        if not executor.belong_concepts:
            return
        matches = {concept.name for concept in executor.belong_concepts} & cls._EXECUTOR_CONCEPTS
        if len(matches) != 1:
            raise WorkflowGraphCompilationError("step_executor must belong to exactly one of Human, Agent, or Program")

    @staticmethod
    def _add_unique[T](values: set[T], value: T, operator_name: str) -> None:
        """Insert one set-backed fact while treating repetition as invalid IR."""

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
        """Assign one scalar/composite-key property exactly once."""

        if key in values:
            raise WorkflowGraphCompilationError(f"duplicate {operator_name}: {key!r}")
        values[key] = value
