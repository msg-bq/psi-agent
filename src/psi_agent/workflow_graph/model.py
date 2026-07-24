from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypedDict


class ResourceRequirementDict(TypedDict):
    resource_id: str
    amount: int


class StepNodeDict(TypedDict):
    step_id: str
    name_id: str
    executor_id: str
    instruction_id: str | None
    timeout_seconds: int | None
    max_attempts: int
    resources: list[ResourceRequirementDict]


class ArtifactNodeDict(TypedDict):
    artifact_id: str
    is_input: bool
    is_output: bool
    binding_step_id: str | None


class ConsumesEdgeDict(TypedDict):
    kind: Literal["consumes"]
    artifact_id: str
    step_id: str


class ProducesEdgeDict(TypedDict):
    kind: Literal["produces"]
    step_id: str
    artifact_id: str


class ForeachEdgeDict(TypedDict):
    kind: Literal["foreach"]
    artifact_id: str
    step_id: str
    item_binding_id: str


type WorkflowEdgeDict = ConsumesEdgeDict | ProducesEdgeDict | ForeachEdgeDict


class WorkflowPolicyDict(TypedDict):
    max_concurrency: int | None
    timeout_seconds: int | None


class WorkflowGraphDict(TypedDict):
    workflow_id: str
    steps: list[StepNodeDict]
    artifacts: list[ArtifactNodeDict]
    edges: list[WorkflowEdgeDict]
    policy: WorkflowPolicyDict


class WorkflowGraphError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ResourceRequirement:
    resource_id: str
    amount: int


@dataclass(frozen=True, slots=True)
class StepNode:
    step_id: str
    name_id: str
    executor_id: str
    instruction_id: str | None = None
    timeout_seconds: int | None = None
    max_attempts: int = 1
    resources: tuple[ResourceRequirement, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.resources, tuple):
            raise WorkflowGraphError("resources must be a tuple")
        if not all(isinstance(requirement, ResourceRequirement) for requirement in self.resources):
            raise WorkflowGraphError("resources must contain only ResourceRequirement")


@dataclass(frozen=True, slots=True)
class ArtifactNode:
    artifact_id: str
    is_input: bool = False
    is_output: bool = False
    binding_step_id: str | None = None


@dataclass(frozen=True, slots=True)
class ConsumesEdge:
    artifact_id: str
    step_id: str
    kind: Literal["consumes"] = field(default="consumes", init=False)


@dataclass(frozen=True, slots=True)
class ProducesEdge:
    step_id: str
    artifact_id: str
    kind: Literal["produces"] = field(default="produces", init=False)


@dataclass(frozen=True, slots=True)
class ForeachEdge:
    artifact_id: str
    step_id: str
    item_binding_id: str
    kind: Literal["foreach"] = field(default="foreach", init=False)


type WorkflowEdge = ConsumesEdge | ProducesEdge | ForeachEdge


@dataclass(frozen=True, slots=True)
class WorkflowPolicy:
    max_concurrency: int | None = None
    timeout_seconds: int | None = None


@dataclass(frozen=True, slots=True)
class WorkflowGraph:
    workflow_id: str
    steps: tuple[StepNode, ...]
    artifacts: tuple[ArtifactNode, ...]
    edges: tuple[WorkflowEdge, ...] = ()
    policy: WorkflowPolicy = WorkflowPolicy()

    def __post_init__(self) -> None:
        self._require_identity(self.workflow_id, "workflow_id")
        if not isinstance(self.steps, tuple):
            raise WorkflowGraphError("steps must be a tuple")
        if not isinstance(self.artifacts, tuple):
            raise WorkflowGraphError("artifacts must be a tuple")
        if not isinstance(self.edges, tuple):
            raise WorkflowGraphError("edges must be a tuple")
        if not isinstance(self.policy, WorkflowPolicy):
            raise WorkflowGraphError("policy must be a WorkflowPolicy")
        if not all(isinstance(step, StepNode) for step in self.steps):
            raise WorkflowGraphError("steps must contain only StepNode")
        if not all(isinstance(artifact, ArtifactNode) for artifact in self.artifacts):
            raise WorkflowGraphError("artifacts must contain only ArtifactNode")
        if not all(isinstance(edge, (ConsumesEdge, ProducesEdge, ForeachEdge)) for edge in self.edges):
            raise WorkflowGraphError("edges must contain only workflow edges")

        step_ids: set[str] = set()
        resource_keys: set[tuple[str, str]] = set()
        for step in self.steps:
            self._require_identity(step.step_id, "step_id")
            self._require_identity(step.name_id, "name_id")
            self._require_identity(step.executor_id, "executor_id")
            if step.instruction_id is not None:
                self._require_identity(step.instruction_id, "instruction_id")
            self._require_positive(
                step.timeout_seconds,
                "timeout_seconds",
                allow_none=True,
            )
            self._require_positive(step.max_attempts, "max_attempts")
            if step.step_id in step_ids:
                raise WorkflowGraphError(f"duplicate step_id: {step.step_id}")
            step_ids.add(step.step_id)
            for requirement in step.resources:
                self._require_identity(requirement.resource_id, "resource_id")
                self._require_positive(requirement.amount, "resource amount")
                resource_key = (step.step_id, requirement.resource_id)
                if resource_key in resource_keys:
                    raise WorkflowGraphError(f"duplicate resource requirement: {resource_key}")
                resource_keys.add(resource_key)

        artifact_ids: set[str] = set()
        artifacts_by_id: dict[str, ArtifactNode] = {}
        for artifact in self.artifacts:
            self._require_identity(artifact.artifact_id, "artifact_id")
            if type(artifact.is_input) is not bool:
                raise WorkflowGraphError("is_input must be a boolean")
            if type(artifact.is_output) is not bool:
                raise WorkflowGraphError("is_output must be a boolean")
            if artifact.binding_step_id is not None:
                self._require_identity(
                    artifact.binding_step_id,
                    "binding_step_id",
                )
            if artifact.artifact_id in artifact_ids:
                raise WorkflowGraphError(f"duplicate artifact_id: {artifact.artifact_id}")
            artifact_ids.add(artifact.artifact_id)
            artifacts_by_id[artifact.artifact_id] = artifact

        shared_ids = step_ids & artifact_ids
        if shared_ids:
            raise WorkflowGraphError(f"identity used by both a step and artifact: {sorted(shared_ids)}")

        for artifact in self.artifacts:
            if artifact.binding_step_id is not None and artifact.binding_step_id not in step_ids:
                raise WorkflowGraphError(f"unknown binding owner step: {artifact.binding_step_id}")
            if artifact.binding_step_id is not None and (artifact.is_input or artifact.is_output):
                raise WorkflowGraphError(f"local binding cannot be a workflow input or output: {artifact.artifact_id}")

        seen_edges: set[WorkflowEdge] = set()
        producers: dict[str, str] = {}
        required_global_artifacts: set[str] = {
            artifact.artifact_id
            for artifact in self.artifacts
            if artifact.is_output and artifact.binding_step_id is None
        }
        foreach_steps: set[str] = set()
        foreach_bindings: set[str] = set()
        for edge in self.edges:
            if edge in seen_edges:
                raise WorkflowGraphError(f"duplicate edge: {edge}")
            seen_edges.add(edge)

            if isinstance(edge, ConsumesEdge):
                self._require_identity(edge.artifact_id, "artifact_id")
                self._require_identity(edge.step_id, "step_id")
                if edge.artifact_id not in artifact_ids:
                    raise WorkflowGraphError(f"unknown consumed artifact: {edge.artifact_id}")
                if edge.step_id not in step_ids:
                    raise WorkflowGraphError(f"unknown consuming step: {edge.step_id}")
                artifact = artifacts_by_id[edge.artifact_id]
                if artifact.binding_step_id is not None and artifact.binding_step_id != edge.step_id:
                    raise WorkflowGraphError(f"local binding consumed by other step: {edge.artifact_id}")
                if artifact.binding_step_id is None:
                    required_global_artifacts.add(edge.artifact_id)
                continue

            if isinstance(edge, ProducesEdge):
                self._require_identity(edge.step_id, "step_id")
                self._require_identity(edge.artifact_id, "artifact_id")
                if edge.step_id not in step_ids:
                    raise WorkflowGraphError(f"unknown producing step: {edge.step_id}")
                if edge.artifact_id not in artifact_ids:
                    raise WorkflowGraphError(f"unknown produced artifact: {edge.artifact_id}")
                artifact = artifacts_by_id[edge.artifact_id]
                if artifact.binding_step_id is not None:
                    raise WorkflowGraphError(f"local binding cannot be produced: {edge.artifact_id}")
                if edge.artifact_id in producers:
                    raise WorkflowGraphError(f"artifact has multiple producers: {edge.artifact_id}")
                producers[edge.artifact_id] = edge.step_id
                continue

            self._require_identity(edge.artifact_id, "artifact_id")
            self._require_identity(edge.step_id, "step_id")
            self._require_identity(edge.item_binding_id, "item_binding_id")
            if edge.artifact_id not in artifact_ids:
                raise WorkflowGraphError(f"unknown foreach source artifact: {edge.artifact_id}")
            if edge.step_id not in step_ids:
                raise WorkflowGraphError(f"unknown foreach step: {edge.step_id}")
            if edge.item_binding_id not in artifact_ids:
                raise WorkflowGraphError(f"unknown foreach item binding: {edge.item_binding_id}")
            source = artifacts_by_id[edge.artifact_id]
            if source.binding_step_id is not None:
                raise WorkflowGraphError(f"local binding cannot be a foreach source: {edge.artifact_id}")
            binding = artifacts_by_id[edge.item_binding_id]
            if binding.binding_step_id != edge.step_id:
                raise WorkflowGraphError(f"foreach binding owner does not match step: {edge.item_binding_id}")
            if edge.item_binding_id in foreach_bindings:
                raise WorkflowGraphError(f"local binding referenced by multiple foreach edges: {edge.item_binding_id}")
            foreach_bindings.add(edge.item_binding_id)
            if edge.step_id in foreach_steps:
                raise WorkflowGraphError(f"step has multiple foreach sources: {edge.step_id}")
            foreach_steps.add(edge.step_id)
            required_global_artifacts.add(edge.artifact_id)

        for artifact in self.artifacts:
            if artifact.binding_step_id is not None and artifact.artifact_id not in foreach_bindings:
                raise WorkflowGraphError(
                    f"local binding must be referenced by exactly one foreach edge: {artifact.artifact_id}"
                )

        for artifact_id in required_global_artifacts:
            artifact = artifacts_by_id[artifact_id]
            if not artifact.is_input and artifact_id not in producers:
                raise WorkflowGraphError(f"global artifact must be an input or producer-backed: {artifact_id}")

        self._require_positive(
            self.policy.max_concurrency,
            "max_concurrency",
            allow_none=True,
        )
        self._require_positive(
            self.policy.timeout_seconds,
            "workflow timeout_seconds",
            allow_none=True,
        )

    def to_dict(self) -> WorkflowGraphDict:
        step_payloads: list[StepNodeDict] = []
        for step in sorted(self.steps, key=lambda item: item.step_id):
            resources = [
                ResourceRequirementDict(
                    resource_id=requirement.resource_id,
                    amount=requirement.amount,
                )
                for requirement in sorted(
                    step.resources,
                    key=lambda item: item.resource_id,
                )
            ]
            step_payloads.append(
                StepNodeDict(
                    step_id=step.step_id,
                    name_id=step.name_id,
                    executor_id=step.executor_id,
                    instruction_id=step.instruction_id,
                    timeout_seconds=step.timeout_seconds,
                    max_attempts=step.max_attempts,
                    resources=resources,
                )
            )

        artifact_payloads = [
            ArtifactNodeDict(
                artifact_id=artifact.artifact_id,
                is_input=artifact.is_input,
                is_output=artifact.is_output,
                binding_step_id=artifact.binding_step_id,
            )
            for artifact in sorted(
                self.artifacts,
                key=lambda item: item.artifact_id,
            )
        ]

        sorted_edges = sorted(
            self.edges,
            key=lambda edge: (
                edge.kind,
                (edge.step_id if isinstance(edge, ProducesEdge) else edge.artifact_id),
                (edge.artifact_id if isinstance(edge, ProducesEdge) else edge.step_id),
                (edge.item_binding_id if isinstance(edge, ForeachEdge) else ""),
            ),
        )
        edge_payloads: list[WorkflowEdgeDict] = []
        for edge in sorted_edges:
            if isinstance(edge, ConsumesEdge):
                edge_payloads.append(
                    ConsumesEdgeDict(
                        kind=edge.kind,
                        artifact_id=edge.artifact_id,
                        step_id=edge.step_id,
                    )
                )
            elif isinstance(edge, ProducesEdge):
                edge_payloads.append(
                    ProducesEdgeDict(
                        kind=edge.kind,
                        step_id=edge.step_id,
                        artifact_id=edge.artifact_id,
                    )
                )
            else:
                edge_payloads.append(
                    ForeachEdgeDict(
                        kind=edge.kind,
                        artifact_id=edge.artifact_id,
                        step_id=edge.step_id,
                        item_binding_id=edge.item_binding_id,
                    )
                )

        return WorkflowGraphDict(
            workflow_id=self.workflow_id,
            steps=step_payloads,
            artifacts=artifact_payloads,
            edges=edge_payloads,
            policy=WorkflowPolicyDict(
                max_concurrency=self.policy.max_concurrency,
                timeout_seconds=self.policy.timeout_seconds,
            ),
        )

    @staticmethod
    def _require_identity(value: object, field_name: str) -> None:
        if not isinstance(value, str) or not value:
            raise WorkflowGraphError(f"{field_name} must be a non-empty string")

    @staticmethod
    def _require_positive(
        value: object,
        field_name: str,
        *,
        allow_none: bool = False,
    ) -> None:
        if allow_none and value is None:
            return
        if type(value) is not int or value < 1:
            raise WorkflowGraphError(f"{field_name} must be a positive integer")
