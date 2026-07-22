from __future__ import annotations

import pytest
from fusion_flow_next.checker import check_workflow
from fusion_flow_next.contracts import CheckResult
from fusion_flow_next.generator import generate_typescript
from fusion_flow_next.parser import parse_workflow
from fusion_flow_next.planning import check_planned_functions


def test_unimplemented_phase_boundaries_fail_explicitly() -> None:
    with pytest.raises(NotImplementedError, match="parser is not implemented"):
        parse_workflow("")
    with pytest.raises(NotImplementedError, match="checker is not implemented"):
        check_workflow(object())
    with pytest.raises(NotImplementedError, match="TypeScript generator is not implemented"):
        generate_typescript(CheckResult(core_ir=object(), diagnostics=(), can_generate=True))
    with pytest.raises(NotImplementedError, match="planning check is not implemented"):
        check_planned_functions((), ())
