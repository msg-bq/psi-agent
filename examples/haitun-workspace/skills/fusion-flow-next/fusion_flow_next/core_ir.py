from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class Concept:
    name: str


@dataclass(frozen=True, slots=True)
class Constant:
    symbol: str
    belong_concepts: tuple[Concept, ...] = ()


@dataclass(frozen=True, slots=True)
class Operator:
    name: str
    input_concepts: tuple[Concept, ...] = ()
    output_concept: Concept | None = None

    @property
    def arity(self) -> int:
        return len(self.input_concepts)


@dataclass(frozen=True, slots=True)
class CompoundTerm:
    operator: Operator
    arguments: tuple[Term, ...]


@dataclass(frozen=True, slots=True)
class ListTerm:
    items: tuple[Term, ...]


@dataclass(frozen=True, slots=True)
class Assertion:
    lhs: Term
    rhs: Term
    relation_symbol: RelationSymbol = "="


@dataclass(frozen=True, slots=True)
class ConnectiveFormula:
    formula_left: Formula
    connective: LogicalConnective
    formula_right: Formula | None = None

    def __post_init__(self) -> None:
        if self.connective == "NOT" and self.formula_right is not None:
            raise ValueError("NOT cannot have a right formula")
        if self.connective != "NOT" and self.formula_right is None:
            raise ValueError(f"{self.connective} requires a right formula")


@dataclass(frozen=True, slots=True)
class IfTerm:
    condition: Formula
    when_true: Term
    when_false: Term


@dataclass(frozen=True, slots=True)
class Workflow:
    name: str
    assertions: tuple[Assertion, ...]


@dataclass(frozen=True, slots=True)
class WorkflowFile:
    constants: tuple[Constant, ...]
    workflows: tuple[Workflow, ...]


type RelationSymbol = Literal["=", "!=", "<", "<=", ">", ">="]
type LogicalConnective = Literal["NOT", "AND", "OR"]
type Term = Constant | CompoundTerm | ListTerm | IfTerm
type Formula = Assertion | ConnectiveFormula
