from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

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


class WorkflowDialect(StrEnum):
    SYNTAX_REVIEW_2026_07_18 = "syntax-review-2026-07-18"
    REPOSITORY_LIST_MULTI = "repository-list-multi"


class GraphProjectionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GraphProjection:
    graph: WorkflowGraph
    residual_assertions: tuple[object, ...]


_MISSING = object()
_EXECUTOR_CONCEPTS = frozenset({"Human", "Agent", "Program"})
_SCALAR_ARITIES = {
    "input_workflow": 2,
    "output_workflow": 2,
    "step_name": 1,
    "step_instruction": 1,
    "step_executor": 1,
    "consumes": 2,
    "produces": 2,
    "foreach_item": 2,
    "step_timeout": 1,
    "max_attempts": 1,
    "resource_requirement": 2,
    "max_concurrency": 1,
    "workflow_timeout": 1,
}
_MULTI_ARITIES = {
    "input_workflow_multi": 1,
    "output_workflow_multi": 1,
    "consumes_multi": 1,
    "produces_multi": 1,
}


def project_workflow(
    workflow: object,
    *,
    dialect: WorkflowDialect,
) -> GraphProjection:
    if not isinstance(dialect, WorkflowDialect):
        raise GraphProjectionError("dialect must be a WorkflowDialect")

    workflow_id = _symbol(workflow, "workflow", attribute="name")
    assertions = getattr(workflow, "assertions", _MISSING)
    if not isinstance(assertions, (tuple, list)):
        raise GraphProjectionError("workflow.assertions must be a tuple or list")

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
    residual: list[object] = []

    for assertion in assertions:
        lhs = getattr(assertion, "lhs", _MISSING)
        rhs = getattr(assertion, "rhs", _MISSING)
        if lhs is _MISSING or rhs is _MISSING:
            raise GraphProjectionError("assertion must expose lhs and rhs")

        operator = getattr(lhs, "operator", _MISSING)
        if operator is _MISSING:
            residual.append(assertion)
            continue
        operator_name = getattr(operator, "name", _MISSING)
        if not isinstance(operator_name, str) or not operator_name:
            raise GraphProjectionError("compound operator must expose a non-empty name")
        arguments = getattr(lhs, "arguments", _MISSING)
        if not isinstance(arguments, (tuple, list)):
            raise GraphProjectionError(f"{operator_name} requires arguments")
        if operator_name not in (_SCALAR_ARITIES | _MULTI_ARITIES):
            residual.append(assertion)
            continue

        relation_symbol = getattr(assertion, "relation_symbol", "=")
        if not isinstance(relation_symbol, str) or relation_symbol not in {"=", "=="}:
            raise GraphProjectionError(f"{operator_name} requires equality, got {relation_symbol!r}")
        expected_arity = _SCALAR_ARITIES.get(operator_name) or _MULTI_ARITIES[operator_name]
        if len(arguments) != expected_arity:
            raise GraphProjectionError(f"{operator_name} expects {expected_arity} arguments, got {len(arguments)}")

        if operator_name in _MULTI_ARITIES:
            if dialect is WorkflowDialect.SYNTAX_REVIEW_2026_07_18 and operator_name != "consumes_multi":
                raise GraphProjectionError(f"{operator_name} is not supported by {dialect.value}")
            item_ids = _multi_symbols(rhs, dialect)
            if operator_name in {
                "input_workflow_multi",
                "output_workflow_multi",
            }:
                _require_owner(arguments[0], workflow_id, operator_name)
                target = input_ids if operator_name == "input_workflow_multi" else output_ids
                for artifact_id in item_ids:
                    _add_unique(target, artifact_id, operator_name)
                    artifact_ids.add(artifact_id)
                continue

            step_id = _symbol(arguments[0], f"{operator_name} step")
            step_ids.add(step_id)
            for artifact_id in item_ids:
                if operator_name == "consumes_multi":
                    _add_unique(
                        consumes,
                        (artifact_id, step_id),
                        operator_name,
                    )
                else:
                    _add_unique(
                        produces,
                        (step_id, artifact_id),
                        operator_name,
                    )
                artifact_ids.add(artifact_id)
            continue

        if operator_name in {"input_workflow", "output_workflow"}:
            _require_owner(arguments[0], workflow_id, operator_name)
            artifact_id = _symbol(arguments[1], f"{operator_name} artifact")
            _require_true(rhs, operator_name)
            target = input_ids if operator_name == "input_workflow" else output_ids
            _add_unique(target, artifact_id, operator_name)
            artifact_ids.add(artifact_id)
            continue

        if operator_name in {"max_concurrency", "workflow_timeout"}:
            _require_owner(arguments[0], workflow_id, operator_name)
            value = _positive_integer(rhs, operator_name)
            if operator_name == "max_concurrency":
                if max_concurrency is not None:
                    raise GraphProjectionError("duplicate max_concurrency")
                max_concurrency = value
            else:
                if workflow_timeout is not None:
                    raise GraphProjectionError("duplicate workflow_timeout")
                workflow_timeout = value
            continue

        step_id = _symbol(arguments[0], f"{operator_name} step")
        step_ids.add(step_id)

        if operator_name == "step_name":
            _set_once(
                step_names,
                step_id,
                _symbol(rhs, "step_name value"),
                "step_name",
            )
        elif operator_name == "step_instruction":
            _set_once(
                step_instructions,
                step_id,
                _symbol(rhs, "step_instruction value"),
                "step_instruction",
            )
        elif operator_name == "step_executor":
            _validate_executor_concepts(rhs)
            _set_once(
                step_executors,
                step_id,
                _symbol(rhs, "step_executor value"),
                "step_executor",
            )
        elif operator_name == "consumes":
            artifact_id = _symbol(arguments[1], "consumed artifact")
            _require_true(rhs, operator_name)
            _add_unique(consumes, (artifact_id, step_id), operator_name)
            artifact_ids.add(artifact_id)
        elif operator_name == "produces":
            artifact_id = _symbol(arguments[1], "produced artifact")
            _require_true(rhs, operator_name)
            _add_unique(produces, (step_id, artifact_id), operator_name)
            artifact_ids.add(artifact_id)
        elif operator_name == "foreach_item":
            source_id = _symbol(arguments[1], "foreach source")
            binding_id = _symbol(rhs, "foreach item binding")
            if step_id in foreach_by_step:
                raise GraphProjectionError(f"duplicate foreach_item for step {step_id!r}")
            if binding_id in binding_owners:
                raise GraphProjectionError(f"duplicate foreach item binding {binding_id!r}")
            foreach_by_step[step_id] = (source_id, binding_id)
            binding_owners[binding_id] = step_id
            artifact_ids.update((source_id, binding_id))
        elif operator_name == "step_timeout":
            _set_once(
                step_timeouts,
                step_id,
                _positive_integer(rhs, operator_name),
                operator_name,
            )
        elif operator_name == "max_attempts":
            _set_once(
                step_attempts,
                step_id,
                _positive_integer(rhs, operator_name),
                operator_name,
            )
        else:
            resource_id = _symbol(arguments[1], "resource identity")
            _set_once(
                resources,
                (step_id, resource_id),
                _positive_integer(rhs, operator_name),
                operator_name,
            )

    for step_id in sorted(step_ids):
        if step_id not in step_names:
            raise GraphProjectionError(f"step {step_id!r} has no step_name")
        if step_id not in step_executors:
            raise GraphProjectionError(f"step {step_id!r} has no step_executor")

    steps = tuple(
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
    )
    artifacts = tuple(
        ArtifactNode(
            artifact_id=artifact_id,
            is_input=artifact_id in input_ids,
            is_output=artifact_id in output_ids,
            binding_step_id=binding_owners.get(artifact_id),
        )
        for artifact_id in sorted(artifact_ids)
    )
    edges = (
        tuple(ConsumesEdge(artifact_id=artifact_id, step_id=step_id) for artifact_id, step_id in sorted(consumes))
        + tuple(
            ForeachEdge(
                artifact_id=source_id,
                step_id=step_id,
                item_binding_id=binding_id,
            )
            for step_id, (source_id, binding_id) in sorted(foreach_by_step.items())
        )
        + tuple(ProducesEdge(step_id=step_id, artifact_id=artifact_id) for step_id, artifact_id in sorted(produces))
    )

    try:
        graph = WorkflowGraph(
            workflow_id=workflow_id,
            steps=steps,
            artifacts=artifacts,
            edges=edges,
            policy=WorkflowPolicy(
                max_concurrency=max_concurrency,
                timeout_seconds=workflow_timeout,
            ),
        )
    except WorkflowGraphError as error:
        raise GraphProjectionError(str(error)) from error

    return GraphProjection(
        graph=graph,
        residual_assertions=tuple(residual),
    )


def _symbol(
    value: object,
    context: str,
    *,
    attribute: str = "symbol",
) -> str:
    symbol = getattr(value, attribute, _MISSING)
    if not isinstance(symbol, str) or not symbol:
        raise GraphProjectionError(f"{context} must expose a non-empty {attribute}")
    return symbol


def _require_owner(value: object, workflow_id: str, operator_name: str) -> None:
    owner_id = _symbol(value, f"{operator_name} owner")
    if owner_id != workflow_id:
        raise GraphProjectionError(f"{operator_name} owner {owner_id!r} does not match workflow {workflow_id!r}")


def _require_true(value: object, operator_name: str) -> None:
    if _symbol(value, f"{operator_name} RHS") != "True":
        raise GraphProjectionError(f"{operator_name} RHS must be the True constant")


def _positive_integer(value: object, operator_name: str) -> int:
    symbol = _symbol(value, f"{operator_name} RHS")
    if not symbol.isascii() or not symbol.isdecimal():
        raise GraphProjectionError(f"{operator_name} RHS must be a positive integer constant")
    try:
        number = int(symbol)
    except ValueError as error:
        raise GraphProjectionError(f"{operator_name} RHS must be a positive integer constant") from error
    if number < 1:
        raise GraphProjectionError(f"{operator_name} RHS must be a positive integer constant")
    return number


def _validate_executor_concepts(value: object) -> None:
    concepts = getattr(value, "belong_concepts", _MISSING)
    if concepts is _MISSING or concepts is None:
        return
    if not isinstance(concepts, (tuple, list)):
        raise GraphProjectionError("step_executor belong_concepts must be a tuple or list")
    if not concepts:
        return
    names: set[str] = set()
    for concept in concepts:
        name = getattr(concept, "name", _MISSING)
        if not isinstance(name, str) or not name:
            raise GraphProjectionError("step_executor belong_concepts entries must expose a name")
        names.add(name)
    matches = names & _EXECUTOR_CONCEPTS
    if len(matches) != 1:
        raise GraphProjectionError("step_executor must belong to exactly one of Human, Agent, or Program")


def _multi_symbols(
    value: object,
    dialect: WorkflowDialect,
) -> tuple[str, ...]:
    if dialect is WorkflowDialect.SYNTAX_REVIEW_2026_07_18:
        if getattr(value, "items", _MISSING) is not _MISSING or getattr(value, "elements", _MISSING) is not _MISSING:
            raise GraphProjectionError("syntax-review consumes_multi requires a members carrier")
        members = getattr(value, "members", _MISSING)
        if members is _MISSING:
            raise GraphProjectionError("syntax-review consumes_multi requires a members carrier")
        return _carrier_symbols(
            members,
            "syntax-review members",
            allow_set=True,
        )

    if getattr(value, "members", _MISSING) is not _MISSING:
        raise GraphProjectionError("repository multi operators require an items or elements carrier")
    items = getattr(value, "items", _MISSING)
    elements = getattr(value, "elements", _MISSING)
    if items is _MISSING and elements is _MISSING:
        raise GraphProjectionError("repository multi operators require an items or elements carrier")

    item_symbols = None if items is _MISSING else _carrier_symbols(items, "repository items", allow_set=False)
    element_symbols = (
        None if elements is _MISSING else _carrier_symbols(elements, "repository elements", allow_set=False)
    )
    if item_symbols is not None and element_symbols is not None and item_symbols != element_symbols:
        raise GraphProjectionError("repository carrier items and elements contain different values")
    return item_symbols if item_symbols is not None else element_symbols or ()


def _carrier_symbols(
    values: object,
    context: str,
    *,
    allow_set: bool,
) -> tuple[str, ...]:
    valid_types = (tuple, list, set, frozenset) if allow_set else (tuple, list)
    if not isinstance(values, valid_types):
        raise GraphProjectionError(f"{context} must be a collection of constants")
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        symbol = _symbol(value, f"{context} item")
        if symbol in seen:
            raise GraphProjectionError(f"duplicate {context} item: {symbol!r}")
        seen.add(symbol)
        result.append(symbol)
    return tuple(result)


def _add_unique[T](
    values: set[T],
    value: T,
    operator_name: str,
) -> None:
    if value in values:
        raise GraphProjectionError(f"duplicate {operator_name}: {value!r}")
    values.add(value)


def _set_once[K, V](
    values: dict[K, V],
    key: K,
    value: V,
    operator_name: str,
) -> None:
    if key in values:
        raise GraphProjectionError(f"duplicate {operator_name}: {key!r}")
    values[key] = value
