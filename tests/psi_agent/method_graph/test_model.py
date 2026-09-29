from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import FrozenInstanceError, dataclass, field
from typing import Literal, cast

import pytest

from psi_agent.method_graph import model as graph_model
from psi_agent.method_graph.model import (
    ArtifactNode,
    ConsumesEdge,
    ForeachEdge,
    ProducesEdge,
    ResourceRequirement,
    StepNode,
    MethodGraph,
    MethodGraphError,
    MethodPolicy,
)


@dataclass(frozen=True, slots=True)
class _DerivedConsumesEdge(ConsumesEdge):
    pass


@dataclass(frozen=True, slots=True)
class _RelabeledConsumesEdge(ConsumesEdge):
    kind: Literal["consumes"] = field(
        default=cast(Literal["consumes"], "produces"),
        init=False,
    )


def test_cycle_is_valid_and_serialization_is_deterministic() -> None:
    s1 = StepNode(
        "s1",
        "draft",
        "writer",
        resources=(
            ResourceRequirement("gpu", 1),
            ResourceRequirement("cpu", 2),
        ),
        independent=True,
        depends_on=("s2",),
    )
    s2 = StepNode("s2", "review", "reviewer")
    a = ArtifactNode("a", is_input=True)
    b = ArtifactNode("b")
    edges = (
        ConsumesEdge("a", "s1"),
        ProducesEdge("s1", "b"),
        ConsumesEdge("b", "s2"),
        ProducesEdge("s2", "a"),
    )

    left = MethodGraph(
        "mtd",
        (s2, s1),
        (b, a),
        tuple(reversed(edges)),
    )
    right = MethodGraph(
        "mtd",
        (s1, s2),
        (a, b),
        edges,
    )

    assert left.to_dict() == right.to_dict()
    payload = left.to_dict()
    assert payload["steps"][0]["executor_id"] == "writer"
    assert "executor_kind" not in payload["steps"][0]
    assert payload["steps"][0]["resources"] == [
        {"resource_id": "cpu", "amount": 2},
        {"resource_id": "gpu", "amount": 1},
    ]
    assert payload["steps"][0]["independent"] is True
    assert payload["steps"][0]["depends_on"] == ["s2"]
    assert [edge["kind"] for edge in payload["edges"]] == [
        "consumes",
        "consumes",
        "produces",
        "produces",
    ]


def test_default_catalog_fields_preserve_the_exact_legacy_payload() -> None:
    graph = MethodGraph(
        "legacy",
        (
            StepNode(
                "step",
                "step-name",
                "agent",
                instruction_id="instruction",
                timeout_seconds=30,
                max_attempts=2,
                resources=(ResourceRequirement("cpu", 2),),
            ),
        ),
        (
            ArtifactNode("input", is_input=True),
            ArtifactNode("output", is_output=True),
        ),
        (
            ConsumesEdge("input", "step"),
            ProducesEdge("step", "output"),
        ),
        policy=MethodPolicy(max_concurrency=1, timeout_seconds=60),
    )

    assert graph.to_dict() == {
        "method_id": "legacy",
        "steps": [
            {
                "step_id": "step",
                "name_id": "step-name",
                "executor_id": "agent",
                "instruction_id": "instruction",
                "timeout_seconds": 30,
                "max_attempts": 2,
                "resources": [{"resource_id": "cpu", "amount": 2}],
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
                "artifact_id": "output",
                "is_input": False,
                "is_output": True,
                "binding_step_id": None,
            },
        ],
        "edges": [
            {
                "kind": "consumes",
                "artifact_id": "input",
                "step_id": "step",
            },
            {
                "kind": "produces",
                "step_id": "step",
                "artifact_id": "output",
            },
        ],
        "policy": {
            "max_concurrency": 1,
            "timeout_seconds": 60,
        },
        "selectors": [],
    }


def test_input_artifact_may_also_have_a_producer() -> None:
    graph = MethodGraph(
        "feedback",
        (StepNode("step", "step-name", "agent"),),
        (ArtifactNode("state", is_input=True, is_output=True),),
        (
            ConsumesEdge("state", "step"),
            ProducesEdge("step", "state"),
        ),
    )

    assert graph.to_dict()["artifacts"] == [
        {
            "artifact_id": "state",
            "is_input": True,
            "is_output": True,
            "binding_step_id": None,
        }
    ]


def test_validation_uses_public_method_graph_error() -> None:
    with pytest.raises(MethodGraphError, match="method_id"):
        MethodGraph("", (), ())


@pytest.mark.parametrize(
    ("component", "field_name", "value"),
    [
        (StepNode("step", "name", "agent"), "step_id", "other"),
        (ArtifactNode("input", is_input=True), "is_input", False),
        (ConsumesEdge("input", "step"), "kind", "other"),
        (MethodGraph("mtd", (), ()), "method_id", "other"),
    ],
)
def test_graph_components_are_frozen(
    component: object,
    field_name: str,
    value: object,
) -> None:
    with pytest.raises(FrozenInstanceError):
        setattr(component, field_name, value)


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda: MethodGraph(
                "mtd",
                cast(tuple[StepNode, ...], [StepNode("step", "name", "agent")]),
                (),
            ),
            "steps must be a tuple",
        ),
        (
            lambda: MethodGraph(
                "mtd",
                (),
                cast(tuple[ArtifactNode, ...], [ArtifactNode("artifact")]),
            ),
            "artifacts must be a tuple",
        ),
        (
            lambda: MethodGraph(
                "mtd",
                (),
                (),
                cast(tuple[ConsumesEdge, ...], []),
            ),
            "edges must be a tuple",
        ),
        (
            lambda: StepNode(
                "step",
                "name",
                "agent",
                resources=cast(
                    tuple[ResourceRequirement, ...],
                    [ResourceRequirement("cpu", 1)],
                ),
            ),
            "resources must be a tuple",
        ),
        (
            lambda: StepNode(
                "step",
                "name",
                "agent",
                depends_on=cast(tuple[str, ...], ["predecessor"]),
            ),
            "depends_on must be a tuple",
        ),
    ],
)
def test_mutable_collections_are_rejected(
    factory: Callable[[], object],
    message: str,
) -> None:
    with pytest.raises(MethodGraphError, match=message):
        factory()


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda: MethodGraph(
                "mtd",
                cast(tuple[StepNode, ...], ("not-step",)),
                (),
            ),
            "steps must contain only StepNode",
        ),
        (
            lambda: MethodGraph(
                "mtd",
                (),
                cast(tuple[ArtifactNode, ...], ("not-artifact",)),
            ),
            "artifacts must contain only ArtifactNode",
        ),
        (
            lambda: MethodGraph(
                "mtd",
                (),
                (),
                cast(tuple[ConsumesEdge, ...], ("not-edge",)),
            ),
            "edges must contain only method edges",
        ),
        (
            lambda: StepNode(
                "step",
                "name",
                "agent",
                resources=cast(
                    tuple[ResourceRequirement, ...],
                    ("not-resource",),
                ),
            ),
            "resources must contain only ResourceRequirement",
        ),
        (
            lambda: MethodGraph(
                "mtd",
                (),
                (),
                policy=cast(MethodPolicy, "not-policy"),
            ),
            "policy must be a MethodPolicy",
        ),
    ],
)
def test_wrong_component_types_use_public_graph_error(
    factory: Callable[[], object],
    message: str,
) -> None:
    with pytest.raises(MethodGraphError, match=message):
        factory()


@pytest.mark.parametrize(
    "edges",
    [
        (
            ConsumesEdge("input", "step"),
            _DerivedConsumesEdge("input", "step"),
        ),
        (_RelabeledConsumesEdge("input", "step"),),
    ],
)
def test_edge_subclasses_are_rejected(
    edges: tuple[ConsumesEdge, ...],
) -> None:
    with pytest.raises(
        MethodGraphError,
        match="edges must contain only method edges",
    ):
        MethodGraph(
            "mtd",
            (StepNode("step", "name", "agent"),),
            (ArtifactNode("input", is_input=True),),
            edges,
        )


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda: MethodGraph(
                "",
                (StepNode("step", "name", "agent"),),
                (),
            ),
            "method_id",
        ),
        (
            lambda: MethodGraph(
                "mtd",
                (StepNode("", "name", "agent"),),
                (),
            ),
            "step_id",
        ),
        (
            lambda: MethodGraph(
                "mtd",
                (StepNode("step", "", "agent"),),
                (),
            ),
            "name_id",
        ),
        (
            lambda: MethodGraph(
                "mtd",
                (StepNode("step", "name", ""),),
                (),
            ),
            "executor_id",
        ),
        (
            lambda: MethodGraph("mtd", (), (ArtifactNode(""),)),
            "artifact_id",
        ),
        (
            lambda: MethodGraph(
                "mtd",
                (
                    StepNode(
                        "step",
                        "name",
                        "agent",
                        instruction_id="",
                    ),
                ),
                (),
            ),
            "instruction_id",
        ),
        (
            lambda: MethodGraph(
                "mtd",
                (
                    StepNode(
                        "step",
                        "name",
                        "agent",
                        resources=(ResourceRequirement("", 1),),
                    ),
                ),
                (),
            ),
            "resource_id",
        ),
        (
            lambda: StepNode(
                "step",
                "name",
                "agent",
                depends_on=("",),
            ),
            "depends_on",
        ),
    ],
)
def test_empty_identities_are_rejected(
    factory: Callable[[], MethodGraph],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        factory()


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda: MethodGraph(
                "mtd",
                (
                    StepNode("duplicate", "first", "agent"),
                    StepNode("duplicate", "second", "agent"),
                ),
                (),
            ),
            "duplicate step",
        ),
        (
            lambda: MethodGraph(
                "mtd",
                (),
                (ArtifactNode("duplicate"), ArtifactNode("duplicate")),
            ),
            "duplicate artifact",
        ),
        (
            lambda: MethodGraph(
                "mtd",
                (StepNode("shared", "name", "agent"),),
                (ArtifactNode("shared"),),
            ),
            "both",
        ),
        (
            lambda: MethodGraph(
                "mtd",
                (
                    StepNode(
                        "step",
                        "name",
                        "agent",
                        resources=(
                            ResourceRequirement("cpu", 1),
                            ResourceRequirement("cpu", 2),
                        ),
                    ),
                ),
                (),
            ),
            "duplicate resource",
        ),
        (
            lambda: StepNode(
                "step",
                "name",
                "agent",
                depends_on=("predecessor", "predecessor"),
            ),
            "duplicate depends_on",
        ),
        (
            lambda: MethodGraph(
                "mtd",
                (StepNode("step", "name", "agent"),),
                (ArtifactNode("input", is_input=True),),
                (
                    ConsumesEdge("input", "step"),
                    ConsumesEdge("input", "step"),
                ),
            ),
            "duplicate edge",
        ),
    ],
)
def test_duplicate_identities_and_relationships_are_rejected(
    factory: Callable[[], MethodGraph],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        factory()


@pytest.mark.parametrize(
    ("edge", "message"),
    [
        (ConsumesEdge("missing", "step"), "artifact"),
        (ConsumesEdge("input", "missing"), "step"),
        (ProducesEdge("missing", "output"), "step"),
        (ProducesEdge("step", "missing"), "artifact"),
        (ForeachEdge("missing", "step", "item"), "artifact"),
        (ForeachEdge("source", "missing", "item"), "step"),
        (ForeachEdge("source", "step", "missing"), "binding"),
    ],
)
def test_missing_edge_endpoints_are_rejected(
    edge: ConsumesEdge | ProducesEdge | ForeachEdge,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        MethodGraph(
            "mtd",
            (StepNode("step", "name", "agent"),),
            (
                ArtifactNode("input", is_input=True),
                ArtifactNode("source", is_input=True),
                ArtifactNode("output"),
                ArtifactNode("item", binding_step_id="step"),
            ),
            (edge,),
        )


@pytest.mark.parametrize(
    "artifact",
    [
        ArtifactNode("missing"),
        ArtifactNode("missing", is_output=True),
    ],
)
def test_consumed_or_output_global_artifact_requires_input_or_producer(
    artifact: ArtifactNode,
) -> None:
    edges: tuple[ConsumesEdge, ...] = ()
    if not artifact.is_output:
        edges = (ConsumesEdge(artifact.artifact_id, "step"),)

    with pytest.raises(ValueError, match="input or producer"):
        MethodGraph(
            "mtd",
            (StepNode("step", "name", "agent"),),
            (artifact,),
            edges,
        )


def test_foreach_source_requires_input_or_producer() -> None:
    with pytest.raises(ValueError, match="input or producer"):
        MethodGraph(
            "mtd",
            (StepNode("step", "name", "agent"),),
            (
                ArtifactNode("source"),
                ArtifactNode("item", binding_step_id="step"),
            ),
            (ForeachEdge("source", "step", "item"),),
        )


def test_artifact_has_at_most_one_producer() -> None:
    with pytest.raises(ValueError, match="multiple producers"):
        MethodGraph(
            "mtd",
            (
                StepNode("left", "left-name", "agent"),
                StepNode("right", "right-name", "agent"),
            ),
            (ArtifactNode("output"),),
            (
                ProducesEdge("left", "output"),
                ProducesEdge("right", "output"),
            ),
        )


def test_step_has_at_most_one_foreach_source() -> None:
    with pytest.raises(ValueError, match="multiple foreach"):
        MethodGraph(
            "mtd",
            (StepNode("step", "name", "agent"),),
            (
                ArtifactNode("left", is_input=True),
                ArtifactNode("right", is_input=True),
                ArtifactNode("item", binding_step_id="step"),
            ),
            (
                ForeachEdge("left", "step", "item"),
                ForeachEdge("right", "step", "item"),
            ),
        )


@pytest.mark.parametrize(
    ("artifacts", "edges", "message"),
    [
        (
            (ArtifactNode("item", binding_step_id="missing"),),
            (),
            "binding owner",
        ),
        (
            (
                ArtifactNode("source", is_input=True),
                ArtifactNode("item", binding_step_id="owner"),
            ),
            (ForeachEdge("source", "other", "item"),),
            "binding owner",
        ),
        (
            (ArtifactNode("item", is_input=True, binding_step_id="owner"),),
            (),
            "method input or output",
        ),
        (
            (ArtifactNode("item", is_output=True, binding_step_id="owner"),),
            (),
            "method input or output",
        ),
        (
            (ArtifactNode("item", binding_step_id="owner"),),
            (ProducesEdge("owner", "item"),),
            "produced",
        ),
        (
            (ArtifactNode("item", binding_step_id="owner"),),
            (ConsumesEdge("item", "other"),),
            "other step",
        ),
        (
            (
                ArtifactNode("item", binding_step_id="owner"),
                ArtifactNode("nested", binding_step_id="owner"),
            ),
            (ForeachEdge("item", "owner", "nested"),),
            "foreach source",
        ),
    ],
)
def test_local_binding_cannot_leak(
    artifacts: tuple[ArtifactNode, ...],
    edges: tuple[ConsumesEdge | ProducesEdge | ForeachEdge, ...],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        MethodGraph(
            "mtd",
            (
                StepNode("owner", "owner-name", "agent"),
                StepNode("other", "other-name", "agent"),
            ),
            artifacts,
            edges,
        )


def test_owner_step_may_consume_its_local_binding() -> None:
    graph = MethodGraph(
        "mtd",
        (StepNode("step", "name", "agent"),),
        (
            ArtifactNode("source", is_input=True),
            ArtifactNode("item", binding_step_id="step"),
        ),
        (
            ForeachEdge("source", "step", "item"),
            ConsumesEdge("item", "step"),
        ),
    )

    assert len(graph.edges) == 2


def test_local_binding_requires_exactly_one_foreach_edge() -> None:
    with pytest.raises(
        MethodGraphError,
        match="exactly one foreach edge",
    ):
        MethodGraph(
            "mtd",
            (StepNode("step", "name", "agent"),),
            (ArtifactNode("item", binding_step_id="step"),),
        )


def test_local_binding_cannot_be_referenced_by_multiple_foreach_edges() -> None:
    with pytest.raises(
        MethodGraphError,
        match="multiple foreach edges",
    ):
        MethodGraph(
            "mtd",
            (StepNode("step", "name", "agent"),),
            (
                ArtifactNode("left", is_input=True),
                ArtifactNode("right", is_input=True),
                ArtifactNode("item", binding_step_id="step"),
            ),
            (
                ForeachEdge("left", "step", "item"),
                ForeachEdge("right", "step", "item"),
            ),
        )


@pytest.mark.parametrize(
    "step",
    [
        StepNode("step", "name", "agent", timeout_seconds=0),
        StepNode("step", "name", "agent", timeout_seconds=True),
        StepNode("step", "name", "agent", max_attempts=0),
        StepNode("step", "name", "agent", max_attempts=True),
        StepNode(
            "step",
            "name",
            "agent",
            resources=(ResourceRequirement("cpu", 0),),
        ),
        StepNode(
            "step",
            "name",
            "agent",
            resources=(ResourceRequirement("cpu", True),),
        ),
    ],
)
def test_step_limits_must_be_positive_integers(step: StepNode) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        MethodGraph("mtd", (step,), ())


@pytest.mark.parametrize("value", [1, "true", None])
def test_independent_requires_an_actual_boolean(
    value: object,
) -> None:
    step = StepNode("step", "name", "agent")
    object.__setattr__(step, "independent", value)

    with pytest.raises(MethodGraphError, match="independent must be a boolean"):
        MethodGraph("mtd", (step,), ())


def test_explicit_step_dependencies_validate_and_round_trip_through_json() -> None:
    graph = MethodGraph(
        "ordered",
        (
            StepNode("third", "third-name", "agent", depends_on=("second", "first")),
            StepNode("first", "first-name", "agent", depends_on=("third", "first")),
            StepNode("second", "second-name", "agent"),
        ),
        (),
    )

    payload = json.loads(json.dumps(graph.to_dict()))

    assert payload["steps"] == [
        {
            "step_id": "first",
            "name_id": "first-name",
            "executor_id": "agent",
            "instruction_id": None,
            "timeout_seconds": None,
            "max_attempts": 1,
            "resources": [],
            "depends_on": ["first", "third"],
        },
        {
            "step_id": "second",
            "name_id": "second-name",
            "executor_id": "agent",
            "instruction_id": None,
            "timeout_seconds": None,
            "max_attempts": 1,
            "resources": [],
        },
        {
            "step_id": "third",
            "name_id": "third-name",
            "executor_id": "agent",
            "instruction_id": None,
            "timeout_seconds": None,
            "max_attempts": 1,
            "resources": [],
            "depends_on": ["first", "second"],
        },
    ]


def test_explicit_step_dependency_references_must_exist() -> None:
    step = StepNode("step", "name", "agent", depends_on=("missing",))

    with pytest.raises(MethodGraphError, match="unknown depends_on step"):
        MethodGraph("mtd", (step,), ())


@pytest.mark.parametrize(
    ("field_name", "component"),
    [
        ("max_attempts", StepNode("step", "name", "agent")),
        ("resource amount", ResourceRequirement("cpu", 1)),
    ],
)
def test_required_positive_integers_reject_none(
    field_name: str,
    component: StepNode | ResourceRequirement,
) -> None:
    if isinstance(component, StepNode):
        object.__setattr__(component, "max_attempts", None)
        step = component
    else:
        object.__setattr__(component, "amount", None)
        step = StepNode(
            "step",
            "name",
            "agent",
            resources=(component,),
        )

    with pytest.raises(MethodGraphError, match=field_name):
        MethodGraph("mtd", (step,), ())


@pytest.mark.parametrize("field_name", ["is_input", "is_output"])
@pytest.mark.parametrize("value", [1, "false", None])
def test_artifact_flags_require_actual_booleans(
    field_name: str,
    value: object,
) -> None:
    artifact = ArtifactNode("artifact")
    object.__setattr__(artifact, field_name, value)

    with pytest.raises(MethodGraphError, match=f"{field_name} must be a boolean"):
        MethodGraph("mtd", (), (artifact,))


@pytest.mark.parametrize(
    "policy",
    [
        MethodPolicy(max_concurrency=0),
        MethodPolicy(max_concurrency=True),
        MethodPolicy(timeout_seconds=0),
        MethodPolicy(timeout_seconds=True),
    ],
)
def test_method_limits_must_be_positive_integers(
    policy: MethodPolicy,
) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        MethodGraph("mtd", (), (), policy=policy)


def test_select_node_serialization_is_deterministic() -> None:
    condition = graph_model.LogicalCondition(
        "and",
        (
            graph_model.ComparisonCondition(
                "eq",
                graph_model.ArtifactOperand("enabled"),
                graph_model.LiteralOperand(True),
            ),
            graph_model.LogicalCondition(
                "not",
                (
                    graph_model.ComparisonCondition(
                        "lt",
                        graph_model.ArtifactOperand("score"),
                        graph_model.LiteralOperand(10),
                    ),
                ),
            ),
        ),
    )
    selector = graph_model.SelectNode(
        "selected",
        "primary",
        "fallback",
        condition,
    )
    graph = MethodGraph(
        "mtd",
        (),
        (
            ArtifactNode("score", is_input=True),
            ArtifactNode("selected", is_output=True),
            ArtifactNode("primary", is_input=True),
            ArtifactNode("fallback", is_input=True),
            ArtifactNode("enabled", is_input=True),
            ArtifactNode("z_selected"),
        ),
        selectors=(
            graph_model.SelectNode(
                "z_selected",
                "primary",
                "fallback",
                condition,
            ),
            selector,
        ),
    )

    selector_payloads = graph.to_dict()["selectors"]
    assert [payload["output_artifact_id"] for payload in selector_payloads] == [
        "selected",
        "z_selected",
    ]
    assert selector_payloads[0] == {
        "output_artifact_id": "selected",
        "when_true_artifact_id": "primary",
        "when_false_artifact_id": "fallback",
        "condition": {
            "kind": "logical",
            "operator": "and",
            "conditions": [
                {
                    "kind": "comparison",
                    "operator": "eq",
                    "left": {
                        "kind": "artifact",
                        "artifact_id": "enabled",
                    },
                    "right": {
                        "kind": "literal",
                        "value": True,
                    },
                },
                {
                    "kind": "logical",
                    "operator": "not",
                    "conditions": [
                        {
                            "kind": "comparison",
                            "operator": "lt",
                            "left": {
                                "kind": "artifact",
                                "artifact_id": "score",
                            },
                            "right": {
                                "kind": "literal",
                                "value": 10,
                            },
                        }
                    ],
                },
            ],
        },
    }


@pytest.mark.parametrize("operator", ["eq", "lt", "lte", "gt", "gte"])
def test_select_comparison_operators_are_serializable(operator: str) -> None:
    condition = graph_model.ComparisonCondition(
        cast(graph_model.ComparisonOperator, operator),
        graph_model.LiteralOperand(1),
        graph_model.LiteralOperand(2),
    )
    selector = graph_model.SelectNode(
        "selected",
        "primary",
        "fallback",
        condition,
    )
    graph = MethodGraph(
        "mtd",
        (),
        (
            ArtifactNode("selected", is_output=True),
            ArtifactNode("primary", is_input=True),
            ArtifactNode("fallback", is_input=True),
        ),
        selectors=(selector,),
    )

    assert graph.to_dict()["selectors"][0]["condition"]["operator"] == operator


def test_select_input_artifact_ids_are_sorted_and_deduplicated() -> None:
    selector = graph_model.SelectNode(
        "selected",
        "candidate",
        "fallback",
        graph_model.LogicalCondition(
            "or",
            (
                graph_model.ComparisonCondition(
                    "eq",
                    graph_model.ArtifactOperand("candidate"),
                    graph_model.ArtifactOperand("condition"),
                ),
                graph_model.ComparisonCondition(
                    "gt",
                    graph_model.ArtifactOperand("condition"),
                    graph_model.LiteralOperand(0),
                ),
            ),
        ),
    )

    assert selector.input_artifact_ids() == (
        "candidate",
        "condition",
        "fallback",
    )


def test_select_output_backs_method_output_and_consumer() -> None:
    selector = graph_model.SelectNode(
        "selected",
        "primary",
        "fallback",
        graph_model.ComparisonCondition(
            "eq",
            graph_model.ArtifactOperand("enabled"),
            graph_model.LiteralOperand(True),
        ),
    )
    graph = MethodGraph(
        "mtd",
        (StepNode("consumer", "consumer-name", "agent"),),
        (
            ArtifactNode("enabled", is_input=True),
            ArtifactNode("primary", is_input=True),
            ArtifactNode("fallback", is_input=True),
            ArtifactNode("selected", is_output=True),
        ),
        (ConsumesEdge("selected", "consumer"),),
        selectors=(selector,),
    )

    assert graph.selectors == (selector,)


@pytest.mark.parametrize(
    ("selector", "message"),
    [
        (
            lambda: graph_model.SelectNode(
                "missing",
                "primary",
                "fallback",
                graph_model.ComparisonCondition(
                    "eq",
                    graph_model.ArtifactOperand("enabled"),
                    graph_model.LiteralOperand(True),
                ),
            ),
            "unknown select output artifact",
        ),
        (
            lambda: graph_model.SelectNode(
                "selected",
                "missing",
                "fallback",
                graph_model.ComparisonCondition(
                    "eq",
                    graph_model.ArtifactOperand("enabled"),
                    graph_model.LiteralOperand(True),
                ),
            ),
            "unknown select input artifact",
        ),
        (
            lambda: graph_model.SelectNode(
                "selected",
                "primary",
                "fallback",
                graph_model.ComparisonCondition(
                    "eq",
                    graph_model.ArtifactOperand("missing"),
                    graph_model.LiteralOperand(True),
                ),
            ),
            "unknown select input artifact",
        ),
    ],
)
def test_missing_select_artifacts_are_rejected(
    selector: Callable[[], object],
    message: str,
) -> None:
    with pytest.raises(MethodGraphError, match=message):
        MethodGraph(
            "mtd",
            (),
            (
                ArtifactNode("enabled", is_input=True),
                ArtifactNode("primary", is_input=True),
                ArtifactNode("fallback", is_input=True),
                ArtifactNode("selected"),
            ),
            selectors=(cast(graph_model.SelectNode, selector()),),
        )


@pytest.mark.parametrize("role", ["output", "candidate", "condition"])
def test_local_artifacts_cannot_be_referenced_by_select(role: str) -> None:
    output_id = "item" if role == "output" else "selected"
    candidate_id = "item" if role == "candidate" else "primary"
    condition_id = "item" if role == "condition" else "enabled"
    selector = graph_model.SelectNode(
        output_id,
        candidate_id,
        "fallback",
        graph_model.ComparisonCondition(
            "eq",
            graph_model.ArtifactOperand(condition_id),
            graph_model.LiteralOperand(True),
        ),
    )

    with pytest.raises(MethodGraphError, match="select artifact must be global"):
        MethodGraph(
            "mtd",
            (StepNode("owner", "owner-name", "agent"),),
            (
                ArtifactNode("source", is_input=True),
                ArtifactNode("item", binding_step_id="owner"),
                ArtifactNode("enabled", is_input=True),
                ArtifactNode("primary", is_input=True),
                ArtifactNode("fallback", is_input=True),
                ArtifactNode("selected"),
            ),
            (ForeachEdge("source", "owner", "item"),),
            selectors=(selector,),
        )


@pytest.mark.parametrize("producer_kind", ["step", "select"])
def test_select_output_cannot_have_multiple_producers(
    producer_kind: str,
) -> None:
    selector = graph_model.SelectNode(
        "selected",
        "primary",
        "fallback",
        graph_model.ComparisonCondition(
            "eq",
            graph_model.ArtifactOperand("enabled"),
            graph_model.LiteralOperand(True),
        ),
    )
    steps: tuple[StepNode, ...] = ()
    edges: tuple[ProducesEdge, ...] = ()
    selectors = (selector, selector)
    if producer_kind == "step":
        steps = (StepNode("producer", "producer-name", "agent"),)
        edges = (ProducesEdge("producer", "selected"),)
        selectors = (selector,)

    with pytest.raises(MethodGraphError, match="multiple producers"):
        MethodGraph(
            "mtd",
            steps,
            (
                ArtifactNode("enabled", is_input=True),
                ArtifactNode("primary", is_input=True),
                ArtifactNode("fallback", is_input=True),
                ArtifactNode("selected"),
            ),
            edges,
            selectors=selectors,
        )


@pytest.mark.parametrize(
    ("selectors", "message"),
    [
        ([], "selectors must be a tuple"),
        (("not-select",), "selectors must contain only SelectNode"),
    ],
)
def test_invalid_select_containers_are_rejected(
    selectors: object,
    message: str,
) -> None:
    with pytest.raises(MethodGraphError, match=message):
        MethodGraph(
            "mtd",
            (),
            (),
            selectors=cast(tuple[graph_model.SelectNode, ...], selectors),
        )


def test_graph_rejects_mutated_select_condition_container() -> None:
    comparison = graph_model.ComparisonCondition(
        "eq",
        graph_model.ArtifactOperand("enabled"),
        graph_model.LiteralOperand(True),
    )
    condition = graph_model.LogicalCondition("not", (comparison,))
    selector = graph_model.SelectNode(
        "selected",
        "primary",
        "fallback",
        condition,
    )
    object.__setattr__(condition, "conditions", [comparison])

    with pytest.raises(MethodGraphError, match="conditions must be a tuple"):
        MethodGraph(
            "mtd",
            (),
            (
                ArtifactNode("enabled", is_input=True),
                ArtifactNode("primary", is_input=True),
                ArtifactNode("fallback", is_input=True),
                ArtifactNode("selected"),
            ),
            selectors=(selector,),
        )


def test_graph_rejects_mutated_select_literal() -> None:
    literal = graph_model.LiteralOperand(True)
    selector = graph_model.SelectNode(
        "selected",
        "primary",
        "fallback",
        graph_model.ComparisonCondition(
            "eq",
            graph_model.ArtifactOperand("enabled"),
            literal,
        ),
    )
    object.__setattr__(literal, "value", [])

    with pytest.raises(MethodGraphError, match="literal value"):
        MethodGraph(
            "mtd",
            (),
            (
                ArtifactNode("enabled", is_input=True),
                ArtifactNode("primary", is_input=True),
                ArtifactNode("fallback", is_input=True),
                ArtifactNode("selected"),
            ),
            selectors=(selector,),
        )


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), float("-inf")],
)
def test_select_literals_must_be_finite(value: float) -> None:
    with pytest.raises(MethodGraphError, match="finite"):
        graph_model.LiteralOperand(value)


@pytest.mark.parametrize(
    ("target", "field_name"),
    [
        ("operand", "artifact_id"),
        ("selector", "when_true_artifact_id"),
        ("selector", "when_false_artifact_id"),
    ],
)
def test_graph_rejects_mutated_select_artifact_ids(
    target: str,
    field_name: str,
) -> None:
    operand = graph_model.ArtifactOperand("enabled")
    selector = graph_model.SelectNode(
        "selected",
        "primary",
        "fallback",
        graph_model.ComparisonCondition(
            "eq",
            operand,
            graph_model.LiteralOperand(True),
        ),
    )
    object.__setattr__(
        operand if target == "operand" else selector,
        field_name,
        [],
    )

    with pytest.raises(MethodGraphError, match="non-empty string"):
        MethodGraph(
            "mtd",
            (),
            (
                ArtifactNode("enabled", is_input=True),
                ArtifactNode("primary", is_input=True),
                ArtifactNode("fallback", is_input=True),
                ArtifactNode("selected"),
            ),
            selectors=(selector,),
        )


def test_select_values_are_frozen() -> None:
    operand = graph_model.ArtifactOperand("enabled")
    condition = graph_model.ComparisonCondition(
        "eq",
        operand,
        graph_model.LiteralOperand(True),
    )
    selector = graph_model.SelectNode(
        "selected",
        "primary",
        "fallback",
        condition,
    )

    for value, field_name in (
        (operand, "artifact_id"),
        (condition, "operator"),
        (selector, "output_artifact_id"),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(value, field_name, "other")
