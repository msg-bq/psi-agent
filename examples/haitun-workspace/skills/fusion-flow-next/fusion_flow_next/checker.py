from __future__ import annotations

from .contracts import CheckResult


def check_workflow(core_ir: object) -> CheckResult:
    del core_ir
    raise NotImplementedError("FusionFlow Next checker is not implemented.")
