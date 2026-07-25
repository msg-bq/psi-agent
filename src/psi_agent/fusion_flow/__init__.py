"""公开 FusionFlow 的运行入口、执行原语与稳定数据模型。"""

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
    TokenSummary,
    TokenUsage,
    aggregate_tokens,
    assert_safe_name,
    format_token_count,
)
from .runtime import RunContext, current_run_context, gc_runs, run


def _legacy_agent(
    config: AgentConfig,
    *,
    runner: SessionRunner | None = None,
) -> Callable[[AgentInvocation], Awaitable[str]]:
    """创建可调用 Agent; 显式 runner 可脱离 ``run()`` 独立执行。"""

    handle = flow.agent(config)

    async def invoke(invocation: AgentInvocation) -> str:
        """优先调用显式 runner, 否则沿用当前 run 的 session 生命周期。"""

        if runner is not None:
            raw = await runner(config, invocation)
            result = raw.text if isinstance(raw, SessionResult) else raw
            if not isinstance(result, str):
                raise TypeError("Agent runner must return SessionResult or str")
            return result
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
    "TokenSummary",
    "TokenUsage",
    "aggregate_tokens",
    "assert_safe_name",
    "flow",
    "format_token_count",
    "gc_runs",
    "run",
]
