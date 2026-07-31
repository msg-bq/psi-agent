from __future__ import annotations

import json
from typing import cast

import anyio
import pytest
from fusion_flow.execution import (
    AgentConfig,
    AgentInvocation,
    ServiceParam,
    SessionResult,
    flow,
    run,
)
from fusion_flow.execution.runtime import RunContext


def test_agent_returns_a_handle_without_an_active_run() -> None:
    config = AgentConfig(name="writer", system_prompt="Write clearly.")

    handle = flow.agent(config)

    assert handle.name == "writer"
    assert handle.config == config
    assert handle.kind == "agent"


@pytest.mark.anyio
async def test_session_requires_runner_only_when_called(tmp_path) -> None:
    handle = flow.agent(AgentConfig(name="writer", system_prompt="Write clearly."))

    async def program(_: RunContext) -> None:
        with pytest.raises(RuntimeError, match="injected runner"):
            await flow.session(handle, "hello")

    result = await run(program, runs_dir=tmp_path, run_id="missing-runner")

    assert result.status == "ok"


@pytest.mark.anyio
async def test_session_requires_exact_context_schema(tmp_path) -> None:
    calls: list[AgentInvocation] = []

    async def runner(
        _: AgentConfig,
        invocation: AgentInvocation,
    ) -> str:
        calls.append(invocation)
        return "ok"

    handle = flow.agent(
        AgentConfig(
            name="writer",
            system_prompt="Write clearly.",
            context_schema=("topic", "language"),
        )
    )

    async def program(_: RunContext) -> None:
        with pytest.raises(ValueError, match="match exactly"):
            await flow.session(handle, "hello", {"topic": "Python"})
        with pytest.raises(ValueError, match="match exactly"):
            await flow.session(
                handle,
                "hello",
                {
                    "topic": "Python",
                    "language": "English",
                    "typo": "extra",
                },
            )
        assert (
            await flow.session(
                handle,
                "hello",
                {"topic": "Python", "language": "English"},
            )
            == "ok"
        )

    result = await run(
        program,
        runs_dir=tmp_path,
        run_id="context-schema",
        runner=runner,
    )

    assert result.status == "ok"
    assert calls == [
        AgentInvocation(
            prompt="hello",
            context={"topic": "Python", "language": "English"},
        )
    ]


@pytest.mark.anyio
async def test_session_applies_defaults_and_ignores_empty_context_schema(
    tmp_path,
) -> None:
    received: list[tuple[AgentConfig, AgentInvocation]] = []

    async def runner(
        config: AgentConfig,
        invocation: AgentInvocation,
    ) -> str:
        received.append((config, invocation))
        return "ok"

    handle = flow.agent(
        AgentConfig(
            name="writer",
            system_prompt="Write clearly.",
            context_schema=(),
        )
    )

    async def program(_: RunContext) -> None:
        assert await flow.session(handle, "hello", {"extra": "allowed"}) == "ok"

    await run(
        program,
        runs_dir=tmp_path,
        run_id="session-defaults",
        runner=runner,
        throw_on_error=True,
    )

    config, invocation = received[0]
    assert config.max_tokens == 8192
    assert config.temperature == 1.0
    assert invocation.context == {"extra": "allowed"}


@pytest.mark.anyio
async def test_session_resume_hash_ignores_tool_order(tmp_path) -> None:
    calls = 0

    async def runner(_: AgentConfig, __: AgentInvocation) -> str:
        nonlocal calls
        calls += 1
        return "cached"

    async def first(_: RunContext) -> None:
        handle = flow.agent(
            AgentConfig(
                name="writer",
                system_prompt="Write clearly.",
                tools=("read", "write"),
            )
        )
        assert await flow.session(handle, "hello") == "cached"

    await run(
        first,
        runs_dir=tmp_path,
        run_id="tool-order",
        runner=runner,
        throw_on_error=True,
    )

    async def resumed(_: RunContext) -> None:
        handle = flow.agent(
            AgentConfig(
                name="writer",
                system_prompt="Write clearly.",
                tools=("write", "read"),
            )
        )
        assert await flow.session(handle, "hello") == "cached"

    await run(
        resumed,
        runs_dir=tmp_path,
        resume_from_run_id="tool-order",
        runner=runner,
        throw_on_error=True,
    )

    assert calls == 1
    meta = json.loads(await anyio.Path(tmp_path, "tool-order", "meta.json").read_text())
    assert meta["session_calls"] == {"writer": 1}
    assert meta["llm_calls"] == 0


@pytest.mark.anyio
async def test_session_failure_does_not_consume_default_binding_number(
    tmp_path,
) -> None:
    calls = 0

    async def runner(
        _: AgentConfig,
        __: AgentInvocation,
    ) -> SessionResult | str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("transient")
        if calls == 2:
            return "plain"
        return SessionResult(text="rich", input_tokens=11, output_tokens=7)

    handle = flow.agent(AgentConfig(name="writer", system_prompt="Write clearly."))

    async def program(_: RunContext) -> None:
        with pytest.raises(RuntimeError, match="transient"):
            await flow.session(handle, "first")
        assert await flow.session(handle, "second") == "plain"
        assert await flow.session(handle, "third") == "rich"

    result = await run(
        program,
        runs_dir=tmp_path,
        run_id="session-numbering",
        runner=runner,
    )
    run_dir = anyio.Path(result.run_dir)

    assert await anyio.Path(run_dir, "bindings", "writer.md").read_text() == "plain"
    assert await anyio.Path(run_dir, "bindings", "writer.2.md").read_text() == "rich"
    assert not await anyio.Path(run_dir, "bindings", "writer.3.md").exists()

    graph = json.loads(await anyio.Path(run_dir, "execution-graph.json").read_text())
    sessions = graph["root"]["children"]
    assert [node["status"] for node in sessions] == ["error", "ok", "ok"]
    assert sessions[1]["tokens"] == {
        "calls": 1,
        "input": None,
        "output": None,
    }
    assert sessions[2]["tokens"] == {
        "calls": 1,
        "input": 11,
        "output": 7,
    }
    assert sessions[1]["metadata"]["binding_name"] == "writer"
    assert sessions[1]["metadata"]["trace_file"] == "trace/writer.json"
    plain_trace = json.loads(await anyio.Path(run_dir, "trace", "writer.json").read_text())
    rich_trace = json.loads(await anyio.Path(run_dir, "trace", "writer.2.json").read_text())
    assert plain_trace["tokens"] == sessions[1]["tokens"]
    assert rich_trace["tokens"] == sessions[2]["tokens"]
    meta = json.loads(await anyio.Path(run_dir, "meta.json").read_text())
    assert meta["session_calls"] == {"writer": 2}


@pytest.mark.anyio
async def test_session_failure_releases_explicit_binding(tmp_path) -> None:
    calls = 0

    async def runner(_: AgentConfig, __: AgentInvocation) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("transient")
        return "saved"

    handle = flow.agent(AgentConfig(name="writer", system_prompt="Write clearly."))

    async def program(_: RunContext) -> None:
        with pytest.raises(RuntimeError, match="transient"):
            await flow.session(
                handle,
                "first",
                binding_name="answer",
            )
        assert (
            await flow.session(
                handle,
                "second",
                binding_name="answer",
            )
            == "saved"
        )
        with pytest.raises(ValueError, match="already exists"):
            await flow.session(
                handle,
                "third",
                binding_name="answer",
            )

    result = await run(
        program,
        runs_dir=tmp_path,
        run_id="explicit-binding",
        runner=runner,
    )

    assert calls == 2
    assert (
        await anyio.Path(
            result.run_dir,
            "bindings",
            "answer.md",
        ).read_text()
        == "saved"
    )


@pytest.mark.anyio
async def test_cancelled_session_releases_default_binding(tmp_path) -> None:
    calls = 0

    async def runner(_: AgentConfig, __: AgentInvocation) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            await anyio.sleep_forever()
        return "recovered"

    handle = flow.agent(AgentConfig(name="writer", system_prompt="Write clearly."))

    async def program(_: RunContext) -> None:
        with anyio.move_on_after(0.2) as cancel_scope:
            await flow.session(handle, "cancel me")
        assert cancel_scope.cancel_called
        assert await flow.session(handle, "retry") == "recovered"

    result = await run(
        program,
        runs_dir=tmp_path,
        run_id="session-cancel",
        runner=runner,
    )
    run_dir = anyio.Path(result.run_dir)

    assert result.status == "ok"
    assert calls == 2
    assert await anyio.Path(run_dir, "bindings", "writer.md").read_text() == "recovered"
    assert not await anyio.Path(run_dir, "bindings", "writer.2.md").exists()
    graph = json.loads(await anyio.Path(run_dir, "execution-graph.json").read_text())
    assert [node["status"] for node in graph["root"]["children"]] == [
        "cancelled",
        "ok",
    ]


@pytest.mark.anyio
async def test_service_validates_registration_and_declared_parameters(
    tmp_path,
) -> None:
    calls: list[dict[str, str]] = []

    async def body(args: dict[str, str]) -> str:
        calls.append(args)
        return f"{args['query']}:{args.get('language', 'default')}"

    async def program(_: RunContext) -> None:
        with pytest.raises(ValueError, match="duplicate service parameter"):
            flow.service(
                "duplicate",
                body,
                params=(
                    ServiceParam(name="query", required=True),
                    ServiceParam(name="query", required=False),
                ),
            )
        handle = flow.service(
            "lookup",
            body,
            params=(
                ServiceParam(name="query", required=True),
                ServiceParam(name="language", required=False),
            ),
        )
        with pytest.raises(ValueError, match="already defined"):
            flow.service("lookup", body)
        with pytest.raises(ValueError, match="missing required"):
            await flow.call(handle, {"language": "zh"})
        with pytest.raises(ValueError, match="unknown arguments"):
            await flow.call(handle, {"query": "Python", "typo": "extra"})

        assert await flow.call(handle, {"query": "Python"}) == "Python:default"
        assert (
            await flow.use(
                "lookup",
                {"query": "AnyIO", "language": "zh"},
            )
            == "AnyIO:zh"
        )

    result = await run(
        program,
        runs_dir=tmp_path,
        run_id="service-call",
        throw_on_error=True,
    )

    assert result.status == "ok"
    assert calls == [
        {"query": "Python"},
        {"query": "AnyIO", "language": "zh"},
    ]
    assert (
        await anyio.Path(
            result.run_dir,
            "bindings",
            "lookup.md",
        ).read_text()
        == "Python:default"
    )
    assert (
        await anyio.Path(
            result.run_dir,
            "bindings",
            "lookup.2.md",
        ).read_text()
        == "AnyIO:zh"
    )
    meta = json.loads(await anyio.Path(result.run_dir, "meta.json").read_text())
    assert meta["service_calls"] == {"lookup": 2}
    graph = json.loads(
        await anyio.Path(result.run_dir, "execution-graph.json").read_text(),
    )
    assert graph["root"]["children"][0]["metadata"] == {
        "service": "lookup",
        "args": {"query": "Python"},
        "binding_name": "lookup",
    }
    assert graph["root"]["children"][1]["metadata"] == {
        "service": "lookup",
        "args": {"query": "AnyIO", "language": "zh"},
        "binding_name": "lookup.2",
    }


@pytest.mark.anyio
async def test_service_resume_hash_preserves_argument_order(tmp_path) -> None:
    calls = 0

    async def body(args: dict[str, str]) -> str:
        nonlocal calls
        calls += 1
        return ",".join(args)

    async def first(_: RunContext) -> None:
        handle = flow.service("ordered", body)
        assert await flow.call(handle, {"a": "1", "b": "2"}) == "a,b"

    await run(
        first,
        runs_dir=tmp_path,
        run_id="argument-order",
        throw_on_error=True,
    )

    async def resumed(_: RunContext) -> None:
        handle = flow.service("ordered", body)
        assert await flow.call(handle, {"b": "2", "a": "1"}) == "b,a"

    await run(
        resumed,
        runs_dir=tmp_path,
        resume_from_run_id="argument-order",
        throw_on_error=True,
    )

    assert calls == 2


@pytest.mark.anyio
async def test_service_body_must_return_a_string_without_committing_binding(
    tmp_path,
) -> None:
    attempts = 0

    async def body(_: dict[str, str]) -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return cast("str", 42)
        return "usable"

    async def program(_: RunContext) -> None:
        handle = flow.service("lookup", body)
        with pytest.raises(TypeError, match="must return a string"):
            await flow.call(handle)
        assert await flow.call(handle) == "usable"

    result = await run(program, runs_dir=tmp_path, run_id="service-result")

    assert result.status == "ok"
    assert (
        await anyio.Path(
            result.run_dir,
            "bindings",
            "lookup.md",
        ).read_text()
        == "usable"
    )
    assert not await anyio.Path(
        result.run_dir,
        "bindings",
        "lookup.2.md",
    ).exists()


@pytest.mark.anyio
async def test_flow_and_run_context_share_single_assignment_state(tmp_path) -> None:
    async def program(context: RunContext) -> None:
        assert await flow.input("topic", "default") == "override"
        with pytest.raises(ValueError, match="already read"):
            await context.input("topic", "again")

        await flow.output("answer", "first")
        with pytest.raises(ValueError, match="already exists"):
            await context.save("answer", "second")

    result = await run(
        program,
        runs_dir=tmp_path,
        run_id="single-assignment",
        inputs={"topic": "override"},
    )

    assert result.status == "ok"
    assert (
        await anyio.Path(
            result.run_dir,
            "input",
            "topic.md",
        ).read_text()
        == "override"
    )
    assert (
        await anyio.Path(
            result.run_dir,
            "bindings",
            "answer.md",
        ).read_text()
        == "first"
    )
