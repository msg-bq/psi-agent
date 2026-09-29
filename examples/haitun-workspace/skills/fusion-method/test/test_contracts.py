from __future__ import annotations

import pytest
from fusion_method import PlannedStep, check_planned_steps
from fusion_method.checker import check_method
from fusion_method.core_ir import Method, MethodFile


def test_unimplemented_phase_boundaries_fail_explicitly() -> None:
    with pytest.raises(NotImplementedError, match="checker is not implemented"):
        check_method(MethodFile((), (Method("example", ()),)))
    with pytest.raises(NotImplementedError, match="planning check is not implemented"):
        check_planned_steps((PlannedStep("example", "Example step", ()),), ())
