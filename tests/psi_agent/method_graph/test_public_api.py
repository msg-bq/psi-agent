from __future__ import annotations

import psi_agent.method_graph as method_graph


def test_method_graph_public_api_contains_only_the_graph_model() -> None:
    expected = {
        "ArtifactOperand",
        "ArtifactOperandDict",
        "ArtifactNode",
        "ArtifactNodeDict",
        "ComparisonCondition",
        "ComparisonConditionDict",
        "ComparisonOperator",
        "ConditionOperand",
        "ConditionOperandDict",
        "ConsumesEdge",
        "ConsumesEdgeDict",
        "ForeachEdge",
        "ForeachEdgeDict",
        "LiteralOperand",
        "LiteralOperandDict",
        "LogicalCondition",
        "LogicalConditionDict",
        "LogicalOperator",
        "ProducesEdge",
        "ProducesEdgeDict",
        "ResourceRequirement",
        "ResourceRequirementDict",
        "SelectCondition",
        "SelectConditionDict",
        "SelectNode",
        "SelectNodeDict",
        "StepNode",
        "StepNodeDict",
        "MethodEdge",
        "MethodEdgeDict",
        "MethodGraph",
        "MethodGraphDict",
        "MethodGraphError",
        "MethodPolicy",
        "MethodPolicyDict",
    }

    assert set(method_graph.__all__) == expected
    assert all(getattr(method_graph, name) is not None for name in expected)
