from __future__ import annotations

import pytest
from fusion_method.core_ir import (
    Assertion,
    CompoundTerm,
    Concept,
    ConnectiveFormula,
    Constant,
    IfTerm,
    ListTerm,
    Method,
    MethodFile,
    Operator,
)


def test_method_core_ir_contract() -> None:
    step = Concept("Step")
    item = Constant("item", (step,))
    operator = Operator("identity", (step,), step)
    assertion = Assertion(CompoundTerm(operator, (item,)), ListTerm((item,)))
    condition = ConnectiveFormula(assertion, "NOT")
    conditional = IfTerm(condition, item, item)
    method = Method("example", (Assertion(conditional, item),))
    method_file = MethodFile((item,), (method,))

    assert operator.arity == 1
    assert not hasattr(assertion, "relation_symbol")
    assert method_file.methods[0].assertions[0].lhs is conditional


def test_connective_formula_rejects_invalid_arity() -> None:
    value = Constant("value")
    assertion = Assertion(value, value)

    with pytest.raises(ValueError, match="NOT cannot have a right formula"):
        ConnectiveFormula(assertion, "NOT", assertion)
    with pytest.raises(ValueError, match="AND requires a right formula"):
        ConnectiveFormula(assertion, "AND")
