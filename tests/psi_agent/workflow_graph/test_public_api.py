from __future__ import annotations

from psi_agent.workflow_graph import (
    ArtifactNode,
    GraphProjection,
    GraphProjectionError,
    StepNode,
    WorkflowDialect,
    WorkflowGraph,
    project_workflow,
)


def test_workflow_graph_public_api_is_importable() -> None:
    assert all(
        value is not None
        for value in (
            ArtifactNode,
            GraphProjection,
            GraphProjectionError,
            StepNode,
            WorkflowDialect,
            WorkflowGraph,
            project_workflow,
        )
    )
