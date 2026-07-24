from __future__ import annotations

import re
import unicodedata
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal


@dataclass(frozen=True, slots=True)
class AgentConfig:
    name: str
    system: str | None = None
    prompt: str | None = None
    model: str | None = None
    max_tokens: int = 8192
    temperature: float = 1.0
    thinking_budget_tokens: int | None = None
    engine: str | None = None
    tools: tuple[str, ...] = ()
    max_turns: int | None = None
    context_schema: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", assert_safe_name(self.name))
        system = self.system if self.system is not None else self.prompt
        if not system:
            raise ValueError("AgentConfig requires a non-empty system / prompt")
        object.__setattr__(self, "system", system)
        object.__setattr__(self, "tools", tuple(self.tools))
        if self.context_schema is not None:
            object.__setattr__(self, "context_schema", tuple(self.context_schema))


@dataclass(frozen=True, slots=True)
class AgentInvocation:
    prompt: str
    context: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if self.context is not None:
            object.__setattr__(
                self,
                "context",
                MappingProxyType(dict(self.context)),
            )


@dataclass(frozen=True, slots=True)
class SessionResult:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None


type SessionRunner = Callable[
    [AgentConfig, AgentInvocation],
    Awaitable[SessionResult | str],
]


@dataclass(frozen=True, slots=True)
class PipelineStep:
    fn: Callable[[object], Awaitable[object]]
    label: str | None = None


@dataclass(frozen=True, slots=True)
class RegexRule:
    pattern: str | re.Pattern[str]
    on: str
    kind: Literal["regex"] = field(default="regex", init=False)


@dataclass(frozen=True, slots=True)
class ContainsRule:
    needle: str
    on: str
    kind: Literal["contains"] = field(default="contains", init=False)


@dataclass(frozen=True, slots=True)
class EqualsRule:
    expected: str
    on: str
    kind: Literal["equals"] = field(default="equals", init=False)


@dataclass(frozen=True, slots=True)
class RangeRule:
    value: float
    minimum: float | None = None
    maximum: float | None = None
    kind: Literal["range"] = field(default="range", init=False)

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int | float):
            raise TypeError("RangeRule value must be numeric")
        if self.minimum is not None and (isinstance(self.minimum, bool) or not isinstance(self.minimum, int | float)):
            raise TypeError("RangeRule minimum must be numeric")
        if self.maximum is not None and (isinstance(self.maximum, bool) or not isinstance(self.maximum, int | float)):
            raise TypeError("RangeRule maximum must be numeric")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("RangeRule minimum must be <= maximum")


@dataclass(frozen=True, slots=True)
class PredicateRule:
    fn: Callable[[], Awaitable[bool] | bool]
    kind: Literal["predicate"] = field(default="predicate", init=False)


type StaticRule = RegexRule | ContainsRule | EqualsRule | RangeRule | PredicateRule


@dataclass(frozen=True, slots=True)
class AgentHandle:
    name: str
    config: AgentConfig
    kind: Literal["agent"] = field(default="agent", init=False)


@dataclass(frozen=True, slots=True)
class ServiceParam:
    name: str
    description: str | None = None
    required: bool = True


@dataclass(frozen=True, slots=True)
class ServiceHandle:
    name: str
    params: tuple[ServiceParam, ...] = ()
    description: str | None = None
    kind: Literal["service"] = field(default="service", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "params", tuple(self.params))


@dataclass(frozen=True, slots=True)
class BlockHandle:
    name: str
    description: str | None = None
    kind: Literal["block"] = field(default="block", init=False)


@dataclass(frozen=True, slots=True)
class ExecResult:
    stdout: str
    raw: str
    exit_code: int
    duration_ms: float
    stderr: str = ""
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class RunResult:
    run_id: str
    run_dir: str
    status: Literal["ok", "error"]


@dataclass(frozen=True, slots=True)
class TokenUsage:
    calls: int
    input: int | None
    output: int | None


type TraceStatus = Literal["running", "ok", "error", "cancelled"]
type TraceKind = Literal[
    "run",
    "session",
    "call",
    "parallel",
    "if",
    "ifBranch",
    "forEach",
    "iteration",
    "evaluate",
    "choice",
    "choiceBranch",
    "loop",
    "pipeline",
    "pipelineStep",
    "retry",
    "block",
    "exec",
    "input",
    "output",
]


@dataclass(slots=True)
class ExecutionTrace:
    trace_id: str
    kind: TraceKind
    label: str
    started_at: str
    status: TraceStatus = "running"
    finished_at: str | None = None
    duration_ms: float | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    children: tuple[ExecutionTrace, ...] = ()
    tokens: TokenUsage | None = None
    cached: bool = False
    metadata: dict[str, object] = field(default_factory=dict)
    error: str | None = None

    def __post_init__(self) -> None:
        self.children = tuple(self.children)
        self.metadata = dict(self.metadata)

    def to_dict(self) -> dict[str, object]:
        tokens = None
        if self.tokens is not None:
            tokens = {
                "calls": self.tokens.calls,
                "input": self.tokens.input,
                "output": self.tokens.output,
            }
        return {
            "trace_id": self.trace_id,
            "kind": self.kind,
            "label": self.label,
            "started_at": self.started_at,
            "status": self.status,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "children": [child.to_dict() for child in self.children],
            "tokens": tokens,
            "cached": self.cached,
            "metadata": dict(self.metadata),
            "error": self.error,
        }


_WINDOWS_RESERVED_NAME = re.compile(
    r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)",
    re.IGNORECASE,
)
_WINDOWS_UNSAFE_CHARACTERS = frozenset('<>:"/\\|?*')


def assert_safe_name(name: str) -> str:
    if not isinstance(name, str) or not name:
        raise ValueError("name must be a non-empty string")

    normalized = unicodedata.normalize("NFC", name)
    if normalized == "." or ".." in normalized:
        raise ValueError(f'name "{name}" must not contain ".."')
    if any(
        character in _WINDOWS_UNSAFE_CHARACTERS or unicodedata.category(character)[0] in {"C", "Z"}
        for character in normalized
    ):
        raise ValueError(f'name "{name}" contains an unsafe character')
    if _WINDOWS_RESERVED_NAME.match(normalized):
        raise ValueError(f'name "{name}" is a Windows reserved device name')
    if normalized.endswith((".", " ")):
        raise ValueError(f'name "{name}" must not end with a period or space')
    return normalized


def aggregate_tokens(root: ExecutionTrace) -> TokenUsage:
    calls = 0
    input_tokens: int | None = 0
    output_tokens: int | None = 0

    def visit(node: ExecutionTrace) -> None:
        nonlocal calls, input_tokens, output_tokens
        if node.cached:
            return
        if node.tokens is not None:
            calls += node.tokens.calls
            if node.tokens.input is None:
                input_tokens = None
            elif input_tokens is not None:
                input_tokens += node.tokens.input
            if node.tokens.output is None:
                output_tokens = None
            elif output_tokens is not None:
                output_tokens += node.tokens.output
        for child in node.children:
            visit(child)

    visit(root)
    return TokenUsage(calls=calls, input=input_tokens, output=output_tokens)


def format_token_count(count: int | None) -> str:
    if count is None:
        return "unknown"
    if count < 1_000:
        return str(count)
    if count < 1_000_000:
        return f"{count / 1_000:.1f}k"
    return f"{count / 1_000_000:.2f}M"
