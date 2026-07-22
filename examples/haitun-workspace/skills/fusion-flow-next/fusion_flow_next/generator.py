from __future__ import annotations

from .contracts import CheckResult, GenerateResult


def generate_typescript(check_result: CheckResult) -> GenerateResult:
    del check_result
    raise NotImplementedError("FusionFlow Next TypeScript generator is not implemented.")
