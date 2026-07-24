from __future__ import annotations

from collections.abc import Awaitable, Callable

from .flow import flow
from .model import (
    AgentConfig,
    AgentHandle,
    AgentInvocation,
    BlockHandle,
    ContainsRule,
    EqualsRule,
    ExecResult,
    ExecutionTrace,
    PipelineStep,
    PredicateRule,
    RangeRule,
    RegexRule,
    RunResult,
    ServiceHandle,
    ServiceParam,
    SessionResult,
    SessionRunner,
    StaticRule,
    TokenUsage,
    aggregate_tokens,
    assert_safe_name,
    format_token_count,
)
from .runtime import RunContext, current_run_context, gc_runs, run


def _legacy_agent(
    config: AgentConfig,
) -> Callable[[AgentInvocation], Awaitable[str]]:
    handle = flow.agent(config)

    async def invoke(invocation: AgentInvocation) -> str:
        context = current_run_context()
        if context.runner is None:
            raise RuntimeError("Agent requires an injected runner")
        return await flow.session(
            handle,
            invocation.prompt,
            invocation.context,
        )

    vars(invoke).update(
        __agentName=handle.name,
        __config=handle.config,
        agent_name=handle.name,
        config=handle.config,
    )
    return invoke


Agent = _legacy_agent


__all__ = [
    "Agent",
    "AgentConfig",
    "AgentHandle",
    "AgentInvocation",
    "BlockHandle",
    "ContainsRule",
    "EqualsRule",
    "ExecResult",
    "ExecutionTrace",
    "PipelineStep",
    "PredicateRule",
    "RangeRule",
    "RegexRule",
    "RunContext",
    "RunResult",
    "ServiceHandle",
    "ServiceParam",
    "SessionResult",
    "SessionRunner",
    "StaticRule",
    "TokenUsage",
    "aggregate_tokens",
    "assert_safe_name",
    "flow",
    "format_token_count",
    "gc_runs",
    "run",
]
