from __future__ import annotations

import inspect
import json
import sys
from functools import partial

import anyio
import pytest

from psi_agent.fusion_flow import (
    AgentConfig,
    AgentInvocation,
    ContainsRule,
    EqualsRule,
    PipelineStep,
    PredicateRule,
    RangeRule,
    RegexRule,
    RunContext,
    flow,
    run,
)


async def _binding_metadata(run_dir: str, name: str) -> dict[str, object]:
    path = anyio.Path(run_dir, "bindings", f"{name}.meta.json")
    payload = json.loads(await path.read_text())
    assert isinstance(payload, dict)
    assert payload["name"] == name
    assert isinstance(payload["produced_by"], str)
    assert payload["produced_by"]
    assert isinstance(payload["produced_at"], str)
    assert payload["produced_at"]
    assert isinstance(payload["source_node"], str)
    assert payload["source_node"]
    return payload


@pytest.mark.anyio
async def test_evaluate_builds_a_typed_json_prompt_and_forwards_context(
    tmp_path,
) -> None:
    invocations: list[AgentInvocation] = []
    responses = iter(('{"value": 5}', '{"value": "blue"}'))

    async def runner(_: AgentConfig, invocation: AgentInvocation) -> str:
        invocations.append(invocation)
        return next(responses)

    context = {"subject": "TS compatibility"}

    async def program(_: RunContext) -> None:
        assert (
            await flow.evaluate(
                question="Score the answer",
                context=context,
                kind="number",
                minimum=2,
                maximum=8,
                integer=True,
                binding_name="score",
            )
            == 5
        )
        assert (
            await flow.evaluate(
                question="Pick a color",
                context=context,
                kind="choice",
                choices=("red", "blue"),
                binding_name="color",
            )
            == "blue"
        )

    result = await run(
        program,
        runs_dir=tmp_path,
        run_id="evaluate-prompt-contract",
        runner=runner,
        throw_on_error=True,
    )

    assert [invocation.context for invocation in invocations] == [context, context]
    number_prompt = invocations[0].prompt.lower()
    for fragment in (
        "score the answer",
        "context.subject",
        "ts compatibility",
        "kind",
        "number",
        "2",
        "8",
        '"value"',
    ):
        assert fragment in number_prompt
    assert "integer" in number_prompt or "整数" in number_prompt
    choice_prompt = invocations[1].prompt.lower()
    for fragment in (
        "pick a color",
        "context.subject",
        "ts compatibility",
        "kind",
        "choice",
        "red",
        "blue",
        '"value"',
    ):
        assert fragment in choice_prompt

    await _binding_metadata(result.run_dir, "score")
    await _binding_metadata(result.run_dir, "color")


@pytest.mark.anyio
async def test_choice_records_question_options_and_chosen_branch(tmp_path) -> None:
    async def runner(_: AgentConfig, invocation: AgentInvocation) -> str:
        assert invocation.context == {"audience": "reader"}
        return '{"value": "beta"}'

    async def selected() -> str:
        return "selected"

    async def program(_: RunContext) -> None:
        assert (
            await flow.choice(
                question="Which branch?",
                context={"audience": "reader"},
                branches=(("alpha", selected), ("beta", selected)),
            )
            == "selected"
        )

    result = await run(
        program,
        runs_dir=tmp_path,
        run_id="choice-trace-contract",
        runner=runner,
        throw_on_error=True,
    )
    graph = json.loads(await anyio.Path(result.run_dir, "execution-graph.json").read_text())
    trace = graph["root"]["children"][0]

    assert trace["kind"] == "choice"
    assert trace["metadata"]["question"] == "Which branch?"
    assert trace["metadata"]["options"] == ["alpha", "beta"]
    assert trace["metadata"]["chosen_label"] == "beta"
    assert trace["metadata"]["chosen_index"] == 1


@pytest.mark.anyio
async def test_loops_pass_zero_based_rounds_and_trace_each_iteration(
    tmp_path,
) -> None:
    contexts: list[RunContext] = []
    until_rounds: list[int] = []
    while_rounds: list[int] = []

    async def program(context: RunContext) -> None:
        contexts.append(context)

        async def until_body(round_index: int) -> None:
            until_rounds.append(round_index)

        async def while_body(round_index: int) -> None:
            while_rounds.append(round_index)

        await flow.loop_until(
            lambda: len(until_rounds) == 2,
            until_body,
            max_iterations=4,
        )
        await flow.loop_while(
            lambda: len(while_rounds) < 2,
            while_body,
            max_iterations=4,
        )

    await run(
        program,
        runs_dir=tmp_path,
        run_id="loop-round-contract",
        throw_on_error=True,
    )

    assert until_rounds == [0, 1]
    assert while_rounds == [0, 1]
    loops = [trace for trace in contexts[0].root_trace.children if trace.kind == "loop"]
    assert len(loops) == 2
    for trace in loops:
        assert [child.kind for child in trace.children] == [
            "iteration",
            "iteration",
        ]
        assert [child.metadata["index"] for child in trace.children] == [0, 1]


@pytest.mark.anyio
async def test_pipeline_step_labels_survive_in_the_trace(tmp_path) -> None:
    contexts: list[RunContext] = []

    async def increment(value: object) -> object:
        assert isinstance(value, int)
        return value + 1

    async def render(value: object) -> object:
        return f"value={value}"

    async def program(context: RunContext) -> None:
        contexts.append(context)
        assert (
            await flow.pipeline(
                1,
                (
                    PipelineStep(label="increment", fn=increment),
                    PipelineStep(label="render", fn=render),
                ),
            )
            == "value=2"
        )

    await run(
        program,
        runs_dir=tmp_path,
        run_id="pipeline-label-contract",
        throw_on_error=True,
    )
    trace = contexts[0].root_trace.children[0]

    assert [child.label for child in trace.children] == ["increment", "render"]
    assert [child.metadata["index"] for child in trace.children] == [0, 1]


@pytest.mark.anyio
async def test_retry_passes_attempt_and_records_outcome_metadata(tmp_path) -> None:
    contexts: list[RunContext] = []
    attempts = 0
    decisions: list[tuple[str, int]] = []

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError(f"temporary-{attempts}")
        return "ok"

    def should_retry(error: BaseException, attempt: int) -> bool:
        decisions.append((str(error), attempt))
        return True

    async def program(context: RunContext) -> None:
        contexts.append(context)
        assert (
            await flow.retry(
                operation,
                max_attempts=4,
                initial_delay=0,
                should_retry=should_retry,
            )
            == "ok"
        )

    await run(
        program,
        runs_dir=tmp_path,
        run_id="retry-contract",
        throw_on_error=True,
    )
    trace = contexts[0].root_trace.children[0]

    assert decisions == [("temporary-1", 1), ("temporary-2", 2)]
    assert trace.metadata["max_attempts"] == 4
    assert trace.metadata["succeeded"] is True
    assert trace.metadata["error_trail"] == [
        "attempt 1: temporary-1",
        "attempt 2: temporary-2",
    ]


@pytest.mark.anyio
async def test_retry_caps_the_first_delay_at_max_delay(tmp_path, monkeypatch) -> None:
    attempts = 0
    delays: list[float] = []

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary")
        return "ok"

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(anyio, "sleep", record_sleep)

    async def program(_: RunContext) -> None:
        assert (
            await flow.retry(
                operation,
                initial_delay=10,
                max_delay=1,
            )
            == "ok"
        )

    await run(
        program,
        runs_dir=tmp_path,
        run_id="retry-delay-cap",
        throw_on_error=True,
    )

    assert delays == [1]


@pytest.mark.anyio
async def test_evaluate_static_uses_discriminated_rules_and_zero_arg_predicate(
    tmp_path,
) -> None:
    predicate_calls = 0
    observed: list[bool] = []
    rules = (
        ("regex", RegexRule(pattern=r"\d+", on="abc123")),
        ("contains", ContainsRule(needle="ell", on="hello")),
        ("equals", EqualsRule(expected="same", on="same")),
        ("range", RangeRule(value=5, minimum=1, maximum=5)),
    )

    def predicate() -> bool:
        nonlocal predicate_calls
        predicate_calls += 1
        return True

    async def program(_: RunContext) -> None:
        for name, rule in rules:
            observed.append(
                await flow.evaluate_static(
                    question=f"Check {name}",
                    rule=rule,
                    binding_name=f"static-{name}",
                )
            )
        observed.append(
            await flow.evaluate_static(
                question="Check predicate",
                rule=PredicateRule(fn=predicate),
                binding_name="static-predicate",
            )
        )

    result = await run(
        program,
        runs_dir=tmp_path,
        run_id="static-rule-contract",
        throw_on_error=True,
    )

    assert observed == [True] * 5
    assert predicate_calls == 1
    for name in ("regex", "contains", "equals", "range", "predicate"):
        payload = json.loads(
            await anyio.Path(
                result.run_dir,
                "bindings",
                f"static-{name}.md",
            ).read_text()
        )
        assert payload == {"value": True, "rule": name}
        await _binding_metadata(result.run_dir, f"static-{name}")


@pytest.mark.anyio
async def test_service_and_block_registration_are_synchronous(tmp_path) -> None:
    service_args: list[dict[str, str]] = []
    block_args: list[dict[str, str]] = []

    async def service_body(args: dict[str, str]) -> str:
        service_args.append(args)
        return args["value"]

    async def block_body(args: dict[str, str]) -> str:
        block_args.append(args)
        return f"{args['left']}:{args['right']}"

    async def program(_: RunContext) -> None:
        service = flow.service("echo", service_body)
        block = flow.define_block("pair", block_body)
        assert not inspect.isawaitable(service)
        assert not inspect.isawaitable(block)
        assert await flow.call(service, {"value": "hello"}) == "hello"
        assert await flow.run_block(block, {"left": "one", "right": "two"}) == "one:two"

    await run(
        program,
        runs_dir=tmp_path,
        run_id="sync-registration-contract",
        throw_on_error=True,
    )

    assert service_args == [{"value": "hello"}]
    assert block_args == [{"left": "one", "right": "two"}]


@pytest.mark.anyio
async def test_parallel_collection_operations_use_iteration_children(
    tmp_path,
) -> None:
    contexts: list[RunContext] = []

    async def double(item: int, _: int) -> int:
        return item * 2

    async def is_odd(item: int, _: int) -> bool:
        return item % 2 == 1

    async def add(total: int, item: int, _: int) -> int:
        return total + item

    async def program(context: RunContext) -> None:
        contexts.append(context)
        assert await flow.pmap([1, 2], double) == [2, 4]
        assert await flow.pfilter([1, 2], is_odd) == [1]
        assert await flow.reduce([1, 2], add, 0) == 3

    await run(
        program,
        runs_dir=tmp_path,
        run_id="collection-trace-contract",
        throw_on_error=True,
    )
    traces = contexts[0].root_trace.children

    assert [trace.kind for trace in traces] == ["forEach", "forEach", "forEach"]
    assert [trace.metadata["parallel"] for trace in traces] == [True, True, False]
    for trace in traces:
        assert [child.kind for child in trace.children] == [
            "iteration",
            "iteration",
        ]
        assert [child.metadata["index"] for child in trace.children] == [0, 1]


@pytest.mark.anyio
async def test_parallel_any_records_every_selected_index(tmp_path) -> None:
    contexts: list[RunContext] = []

    async def value(label: str, delay: float) -> str:
        await anyio.sleep(delay)
        return label

    async def never() -> str:
        await anyio.sleep_forever()
        raise AssertionError("unreachable")

    async def program(context: RunContext) -> None:
        contexts.append(context)
        assert await flow.parallel(
            (
                partial(value, "first", 0),
                partial(value, "second", 0.01),
                never,
            ),
            join="any",
            any_count=2,
        ) == ["first", "second"]

    await run(
        program,
        runs_dir=tmp_path,
        run_id="parallel-selected-indexes-contract",
        throw_on_error=True,
    )
    trace = contexts[0].root_trace.children[0]

    assert trace.metadata["selected_indexes"] == [0, 1]


@pytest.mark.anyio
async def test_exec_name_is_trace_label_and_default_binding_prefix(tmp_path) -> None:
    async def program(_: RunContext) -> None:
        result = await flow.exec(
            "named-command",
            (sys.executable, "-c", "print('ok')"),
        )
        assert result.stdout == "ok"

    result = await run(
        program,
        runs_dir=tmp_path,
        run_id="exec-name-contract",
        throw_on_error=True,
    )
    graph = json.loads(await anyio.Path(result.run_dir, "execution-graph.json").read_text())
    trace = graph["root"]["children"][0]

    assert trace["kind"] == "exec"
    assert trace["label"] == "named-command"
    assert (
        await anyio.Path(
            result.run_dir,
            "bindings",
            "named-command.md",
        ).read_text()
        == "ok"
    )
    metadata = await _binding_metadata(result.run_dir, "named-command")
    assert metadata["produced_by"] == "named-command"
