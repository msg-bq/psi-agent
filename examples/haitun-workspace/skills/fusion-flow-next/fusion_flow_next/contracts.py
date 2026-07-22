from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

type DiagnosticSeverity = Literal["error", "warning"]


@dataclass(frozen=True, slots=True)
class SourcePosition:
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class SourceSpan:
    start: SourcePosition
    end: SourcePosition


@dataclass(frozen=True, slots=True)
class Diagnostic:
    severity: DiagnosticSeverity
    message: str
    span: SourceSpan | None = None
    design_reference: str | None = None


@dataclass(frozen=True, slots=True)
class ParseResult:
    core_ir: object | None
    diagnostics: tuple[Diagnostic, ...]


@dataclass(frozen=True, slots=True)
class CheckResult:
    core_ir: object
    diagnostics: tuple[Diagnostic, ...]
    can_generate: bool


@dataclass(frozen=True, slots=True)
class GenerateResult:
    code: str | None
    diagnostics: tuple[Diagnostic, ...]
