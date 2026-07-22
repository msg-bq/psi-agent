from __future__ import annotations

from dataclasses import dataclass

from .contracts import Diagnostic


@dataclass(frozen=True, slots=True)
class PlannedSyntax:
    description: str
    name: str | None


@dataclass(frozen=True, slots=True)
class PlannedFunction:
    id: str
    description: str
    syntax: tuple[PlannedSyntax, ...]


@dataclass(frozen=True, slots=True)
class PlanningCheckResult:
    can_author_workflow: bool
    diagnostics: tuple[Diagnostic, ...]


def check_planned_functions(
    functions: tuple[PlannedFunction, ...],
    available_syntax_names: tuple[str, ...],
) -> PlanningCheckResult:
    del functions, available_syntax_names
    raise NotImplementedError("FusionFlow Next planning check is not implemented.")
