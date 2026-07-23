"""Validate planned DSL capabilities before workflow authoring."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import Diagnostic


@dataclass(frozen=True, slots=True)
class PlannedSyntax:
    """DSL syntax required by a planned function.

    ``name=None`` means no matching syntax was found; callers must not invent
    one. Non-null names must be non-empty after trimming.
    """

    description: str
    name: str | None


@dataclass(frozen=True, slots=True)
class PlannedFunction:
    """Planned function with at least one required syntax mapping."""

    id: str
    description: str
    syntax: tuple[PlannedSyntax, ...]


@dataclass(frozen=True, slots=True)
class PlanningCheckResult:
    """Whether declared functions can be authored, independent of later phases."""

    can_author_workflow: bool
    diagnostics: tuple[Diagnostic, ...]


def check_planned_functions(
    functions: tuple[PlannedFunction, ...],
    available_syntax_names: tuple[str, ...],
) -> PlanningCheckResult:
    """Check planned functions after planning and before authoring the DSL.

    The caller supplies syntax names that actually exist; a non-empty mapping
    is not assumed to be available. Missing, blank, unavailable, or empty
    mappings are normal diagnostics and make ``can_author_workflow`` false.
    This phase checks declared items only and cannot prove the planner listed
    every required function. It does not imply parse, compile, or execution
    success.

    The current stub raises only because this phase is not implemented.
    """

    del functions, available_syntax_names
    raise NotImplementedError("FusionFlow Next planning check is not implemented.")
