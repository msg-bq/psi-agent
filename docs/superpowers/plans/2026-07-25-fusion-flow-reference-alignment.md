# FusionFlow Reference Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align PR #15 with the approved observable contracts from the attached TypeScript runtime.

**Architecture:** Reuse `RunContext` as the single owner of binding reservations,
call ordinals, trace persistence, and snapshots. Keep `Flow` as the thin
orchestration layer and add only the public data needed for grouped token totals
and explicit standalone runners.

**Tech Stack:** Python 3.14, AnyIO, pytest, Ruff, ty.

---

### Task 1: Transactional resume bindings

**Files:**
- Modify: `src/psi_agent/fusion_flow/runtime.py`
- Modify: `src/psi_agent/fusion_flow/flow.py`
- Test: `tests/psi_agent/fusion_flow/test_runtime.py`
- Test: `tests/psi_agent/fusion_flow/test_ts_semantic_contracts.py`

- [ ] **Step 1: Write failing regression tests**

```python
@pytest.mark.anyio
async def test_failed_session_retry_reuses_same_resume_ordinal(tmp_path):
    attempts = 0

    async def seed_body(args: dict[str, str]) -> str:
        return args["value"]

    async def seed(_: RunContext) -> None:
        service = flow.service("worker", seed_body)
        await flow.call(service, {"value": "old-one"})
        await flow.call(service, {"value": "old-two"})

    await run(seed, runs_dir=tmp_path, run_id="resume-ordinal", throw_on_error=True)

    async def refreshed_body(_: dict[str, str]) -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("retry me")
        return "fresh"

    async def resumed(_: RunContext) -> None:
        service = flow.service("worker", refreshed_body)
        with pytest.raises(RuntimeError, match="retry me"):
            await flow.call(service, {"value": "changed"})
        assert await flow.call(service, {"value": "changed"}) == "fresh"

    result = await run(
        resumed,
        runs_dir=tmp_path,
        resume_from_run_id="resume-ordinal",
        throw_on_error=True,
    )
    assert await anyio.Path(result.run_dir, "bindings", "worker.md").read_text() == "fresh"
    assert not await anyio.Path(result.run_dir, "bindings", "worker.3.md").exists()


@pytest.mark.anyio
async def test_explicit_resume_miss_replaces_old_binding_once(tmp_path):
    async def body(args: dict[str, str]) -> str:
        return args["value"]

    async def seed(_: RunContext) -> None:
        await flow.call(flow.service("fixed-service", body), {"value": "old"}, binding_name="fixed")

    await run(seed, runs_dir=tmp_path, run_id="explicit-resume", throw_on_error=True)

    async def resumed(_: RunContext) -> None:
        service = flow.service("fixed-service", body)
        assert await flow.call(service, {"value": "new"}, binding_name="fixed") == "new"
        with pytest.raises(ValueError, match="already exists"):
            await flow.call(service, {"value": "again"}, binding_name="fixed")

    result = await run(
        resumed,
        runs_dir=tmp_path,
        resume_from_run_id="explicit-resume",
        throw_on_error=True,
    )
    assert await anyio.Path(result.run_dir, "bindings", "fixed.md").read_text() == "new"
```

- [ ] **Step 2: Verify RED**

Run:
`uv run pytest -q tests/psi_agent/fusion_flow/test_ts_semantic_contracts.py -k "resume_ordinal or explicit_resume_miss"`

Expected: failures show early ordinal mutation and old resume bindings treated as
current-run writes.

- [ ] **Step 3: Implement provisional call reservations**

Make resume bindings read-only cache input, not members of the current-run
written-name set. Reserve the candidate ordinal/name before lookup, commit the
ordinal only on cache hit or successful binding persistence, and release both on
failure.

- [ ] **Step 4: Verify GREEN**

Run the command from Step 2 and the complete FusionFlow runtime tests.

### Task 2: `exec()` pipe ordering and truncation

**Files:**
- Modify: `src/psi_agent/fusion_flow/flow.py`
- Test: `tests/psi_agent/fusion_flow/test_flow_evaluate_exec.py`

- [ ] **Step 1: Write failing regression tests**

```python
@pytest.mark.anyio
async def test_exec_drains_output_while_sending_large_stdin(tmp_path):
    size = 256 * 1024
    script = (
        "import sys;"
        f"sys.stdout.buffer.write(b'x'*{size});sys.stdout.buffer.flush();"
        "data=sys.stdin.buffer.read();sys.stdout.buffer.write(str(len(data)).encode())"
    )
    observed: list[ExecResult] = []

    async def program(_: RunContext) -> None:
        observed.append(
            await flow.exec("duplex", (sys.executable, "-c", script), stdin=b"y" * size)
        )

    with anyio.fail_after(5):
        await run(program, runs_dir=tmp_path, run_id="duplex", throw_on_error=True)
    assert observed[0].raw.endswith(str(size))


@pytest.mark.anyio
async def test_exec_limit_kills_and_marks_binding(tmp_path):
    script = "import sys\nwhile True:\n sys.stdout.buffer.write(b'x'*4096)\n sys.stdout.flush()"
    observed: list[ExecResult] = []

    async def program(_: RunContext) -> None:
        observed.append(
            await flow.exec(
                "limited",
                (sys.executable, "-c", script),
                output_limit=1024,
                timeout_seconds=5,
            )
        )

    result = await run(program, runs_dir=tmp_path, run_id="limited", throw_on_error=True)
    binding = await anyio.Path(result.run_dir, "bindings", "limited.md").read_text()
    assert observed[0].raw == "x" * 1024
    assert observed[0].truncated is True
    assert "[truncated at 1024 bytes" in binding


@pytest.mark.anyio
@pytest.mark.parametrize("limit", [0, math.inf])
async def test_exec_can_disable_output_limit(tmp_path, limit):
    observed: list[ExecResult] = []

    async def program(_: RunContext) -> None:
        observed.append(
            await flow.exec(
                "unlimited",
                (sys.executable, "-c", "print('complete')"),
                output_limit=limit,
            )
        )

    await run(program, runs_dir=tmp_path, run_id=f"unlimited-{limit}", throw_on_error=True)
    assert observed[0].stdout == "complete"
    assert observed[0].truncated is False
```

- [ ] **Step 2: Verify RED**

Run:
`uv run pytest -q tests/psi_agent/fusion_flow/test_flow_evaluate_exec.py -k "large_stdin or kills_and_marks or disable_output_limit"`

Expected: deadlock timeout, non-terminating producer, missing marker, and rejected
disabled-limit values.

- [ ] **Step 3: Implement concurrent I/O**

Start stdout/stderr readers and stdin sender inside one AnyIO task group under
the timeout scope. Kill on stdout overflow, retain exactly the prefix, treat
that kill as truncated success, and append the diagnostic marker only to the
persisted binding.

- [ ] **Step 4: Verify GREEN**

Run the command from Step 2 and all exec tests.

### Task 3: Incremental progress and grouped tokens

**Files:**
- Modify: `src/psi_agent/fusion_flow/model.py`
- Modify: `src/psi_agent/fusion_flow/runtime.py`
- Modify: `src/psi_agent/fusion_flow/flow.py`
- Modify: `src/psi_agent/fusion_flow/__init__.py`
- Test: `tests/psi_agent/fusion_flow/test_model.py`
- Test: `tests/psi_agent/fusion_flow/test_runtime.py`
- Test: `tests/psi_agent/fusion_flow/test_public_api.py`

- [ ] **Step 1: Write failing tests**

```python
def test_aggregate_tokens_separates_user_and_internal():
    root = ExecutionTrace(
        trace_id="root",
        kind="run",
        label="run",
        started_at="2026-07-25T00:00:00Z",
        children=(
            ExecutionTrace(
                trace_id="user",
                kind="session",
                label="writer",
                started_at="2026-07-25T00:00:00Z",
                tokens=TokenUsage(calls=1, input=4, output=2),
                metadata={"agent": "writer"},
            ),
            ExecutionTrace(
                trace_id="internal",
                kind="evaluate",
                label="judge",
                started_at="2026-07-25T00:00:00Z",
                tokens=TokenUsage(calls=1, input=3, output=1),
                metadata={"evaluator_agent": "__evaluator__"},
            ),
        ),
    )
    totals = aggregate_tokens(root)
    assert totals.user.calls == 1
    assert totals.internal.calls == 1
    assert totals.calls == 2


@pytest.mark.anyio
async def test_progress_records_paired_start_and_end_events(tmp_path):
    async def program(_: RunContext) -> None:
        await flow.block("step", lambda: anyio.sleep(0))

    result = await run(program, runs_dir=tmp_path, run_id="progress", throw_on_error=True)
    raw = await anyio.Path(result.run_dir, "progress.jsonl").read_text()
    events = [json.loads(line) for line in raw.splitlines()]
    starts = {event["id"]: event for event in events if event["event"] == "node_start"}
    ends = {event["id"]: event for event in events if event["event"] == "node_end"}
    assert starts.keys() == ends.keys()
    assert all(event["status"] == "ok" for event in ends.values())
```

- [ ] **Step 2: Verify RED**

Run:
`uv run pytest -q tests/psi_agent/fusion_flow/test_model.py tests/psi_agent/fusion_flow/test_runtime.py -k "separates_user or paired_start"`

- [ ] **Step 3: Implement the artifact contracts**

Add one grouped total model that retains flat total properties. Write compact
TypeScript-compatible progress events at trace entry and exit; keep writes
best-effort and serialized by the existing lock.

- [ ] **Step 4: Verify GREEN**

Run the command from Step 2 and public API tests.

### Task 4: Public compatibility conveniences

**Files:**
- Modify: `src/psi_agent/fusion_flow/__init__.py`
- Modify: `src/psi_agent/fusion_flow/runtime.py`
- Test: `tests/psi_agent/fusion_flow/test_public_api.py`
- Test: `tests/psi_agent/fusion_flow/test_runtime.py`

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.anyio
async def test_agent_with_explicit_runner_is_callable_outside_run():
    config = AgentConfig(name="standalone", system="Answer")

    async def runner(_: AgentConfig, invocation: AgentInvocation) -> str:
        return f"ok:{invocation.prompt}"

    agent = Agent(config, runner=runner)
    assert await agent(AgentInvocation(prompt="hi")) == "ok:hi"


@pytest.mark.anyio
async def test_context_exposes_package_flow_and_defaults_program_snapshot(
    tmp_path,
    monkeypatch,
):
    entry = anyio.Path(tmp_path, "entry.py")
    await entry.write_text("print('entry')\n")
    monkeypatch.setattr(sys, "argv", [str(entry)])

    async def program(context: RunContext) -> None:
        assert context.flow is flow

    result = await run(program, runs_dir=tmp_path, run_id="snapshot", throw_on_error=True)
    assert await anyio.Path(result.run_dir, "program.py").read_text() == "print('entry')\n"
```

- [ ] **Step 2: Verify RED**

Run:
`uv run pytest -q tests/psi_agent/fusion_flow/test_public_api.py tests/psi_agent/fusion_flow/test_runtime.py -k "explicit_runner or exposes_package_flow"`

- [ ] **Step 3: Implement minimal compatibility**

Accept keyword-only `runner` in `Agent`, expose the singleton through a lazy
`RunContext.flow` property, and best-effort snapshot a `.py` entry from
`sys.argv[0]` when no explicit path is supplied.

- [ ] **Step 4: Verify GREEN**

Run the command from Step 2.

### Task 5: Documentation, review, and full verification

**Files:**
- Modify: `docs/architecture/workflow/2026-07-23-fusion-flow-python-runtime-design.zh.md`
- Modify as needed: `README.md`, `README_en.md`, `AGENTS.md`
- Review: all files changed by Tasks 1-4

- [ ] **Step 1: Update behavior documentation and detailed comments**

Document transactional resume semantics, truncation behavior, progress event
shape, grouped token totals, and the three intentional Python differences.

- [ ] **Step 2: Run focused and full verification**

```text
uv run pytest -q tests/psi_agent/fusion_flow
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
```

- [ ] **Step 3: Run a clean independent review**

Give a fresh subagent only the approved spec, final diff, attachment path, and
test commands. Fix every confirmed contract gap and repeat until the reviewer
returns no blocking finding.

- [ ] **Step 4: Confirm intentional differences remain covered**

Keep tests proving `parallel()` waits for cooperative sibling cleanup,
`Agent()` without a runner still requires an active run, and configuration
constructors remain `snake_case`.
