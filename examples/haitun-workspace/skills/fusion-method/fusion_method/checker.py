"""Static method checks over successfully parsed Core IR."""

from __future__ import annotations

from .contracts import CheckResult
from .core_ir import MethodFile


def check_method(core_ir: MethodFile) -> CheckResult:
    """Validate method semantics without parsing, compiling, or executing.

    The checker owns operator contracts and arity, duplicates, reference
    integrity, and other static method rules. For example, S01 requires the
    first argument of ``input_method`` and ``output_method`` to equal the
    enclosing method name. Ordinary method failures belong in the returned
    diagnostics; this stub raises only because checking is not implemented.

    This phase validates Core IR but does not build or rewrite backend shapes.
    """

    del core_ir
    raise NotImplementedError("FusionMethod checker is not implemented.")
