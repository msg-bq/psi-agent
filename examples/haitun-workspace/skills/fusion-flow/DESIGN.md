# FusionFlow G4 durable execution design

## Status and scope

This document defines the runtime contract for:

- interpreting the G4 workflow graph while reusing the Python Flow execution
  kernels instead of duplicating generic retry and indexed fan-out;
- dispatching Agent Steps through the Python `flow.agent()` / `flow.session()` API;
- executing `foreach_item` as durable per-item Step instances;
- applying Step resources, timeouts, retries, output validation, and checkpoints to
  those instances.

The existing G4 `if(condition, true_artifact, false_artifact)` remains an eager
value selector. Lazy conditional subgraphs are deliberately out of scope and are
tracked in [msg-bq/psi-agent#80](https://github.com/msg-bq/psi-agent/issues/80).

## Runtime layers

The G4 runtime has four semantic layers:

1. The parser and compiler lower declarations into an immutable graph and
   catalog-owned executor configuration.
2. Private top-level helpers in `fusion_flow.execution.flow` provide a shared,
   `RunContext`-free execution kernel for retry sequencing, bounded indexed
   parallel traversal, plus deterministic G4 foreach aggregation.
3. The durable graph interpreter owns graph readiness and interpretation,
   Artifact state, checkpoint/resume, global admission, resources, and
   workflow/Step timeout. It supplies G4 policies and persistence hooks to the
   shared kernel instead of implementing a second retry or foreach scheduler.
4. Leaf executor adapters run Agent, Program, or Human work. The Agent adapter
   uses `flow.agent()` and `flow.session()` rather than implementing another
   session protocol.

Public `flow.parallel()`, `flow.if_()`, `flow.for_each()`, and `flow.retry()` are
immediate Python callback combinators, not graph bytecode. The G4 interpreter
does not mechanically lower graph instructions into those public calls.
Where their semantics overlap, the public Flow API and the G4 interpreter call
the same private retry/indexed-traversal kernels and add their own policy and
state layers. The graph-facing aggregation helper stays in the same `flow.py`
mechanism layer even though the public Flow API has no aligned-error Artifact
contract.

## Shared execution kernel contract

The shared helpers live in `fusion_flow/execution/flow.py`, but they must be
callable without an active `execution.run()`. The retry and indexed-traversal
kernels must not call `current_run_context()` or know about Flow
bindings/traces, WorkflowGraph types, Artifacts, checkpoints, resource
allocators, or executor kinds. The aggregation helper is a stateless value
transform: it accepts Artifact IDs only as opaque mapping keys and knows
nothing about graph topology, readiness, commits, or checkpoints.

The kernel provides mechanisms rather than one hard-coded policy:

- retry sequencing reports a one-based attempt and accepts explicit retry
  classification, so cancellation, Human suspension, and execution invariants
  can escape without being retried;
- bounded indexed parallel traversal preserves source indexes, supports an
  explicit concurrency bound, and exposes terminal outcomes without forcing
  either fail-fast or error collection on every caller;
- indexed/foreach aggregation is deterministic by source index, including
  empty input, successful `null`, and aligned terminal errors.

The public Flow API adds its active-run requirement, traces and existing
TypeScript-compatible fail-fast/retry-backoff behavior around the shared retry
and indexed-traversal helpers. The G4 interpreter adds per-attempt global
admission and resource leases, exact output validation, ordinary-error
collection, per-iteration checkpoint hooks, graph-facing aggregation, and
Artifact publication. Step and workflow timeout may remain in
`workflow_execution`; timeout does not need to move into the shared kernel.

Sharing the mechanism must not collapse the two public contracts. In
particular, G4 control signals and invariant errors must still escape, and a
Flow fail-fast collection must not silently adopt G4's aligned-error behavior.

## Agent Step contract

The compiler consumes every Agent-owned G4 declaration and produces one immutable
runtime configuration per Agent identity:

- `agent_config(Agent, Model, Engine, ApiBase)`;
- `agent_system_prompt(Agent)`;
- `allowed_tool(Agent, Tool)`;
- `max_output_tokens(Agent)`;
- `temperature(Agent)`;
- `reasoning_effort(Agent)`;
- `max_turns(Agent)`.

Unknown, duplicate, type-invalid, or unsupported routing declarations fail
closed. A declaration must never parse successfully and then be silently
ignored.

The workspace adapter wraps one complete G4 workflow execution in one legacy
`execution.run()` and injects a production `SessionRunner`. Each Agent executor
has one immutable `AgentHandle`; every logical Step instance calls:

```python
await flow.session(
    handle,
    prompt,
    context=serialized_invocation_context,
    binding_name=stable_invocation_id,
)
```

The injected runner retains the current workspace `SessionAgent` tool loop,
non-recursion denylist, resource context, and exact `submit_step_result` schema.
It must validate and normalize all declared Artifact outputs before returning a
successful `SessionResult`. Therefore `flow.session()` can never commit an
invalid structured result as a successful binding.

The fixed Step safety/output protocol and the declared Agent system prompt are
separate layers. User configuration may augment the fixed protocol but may not
remove the non-recursion rule, workspace boundary, or exact-output contract.
`allowed_tool` is intersected with the host-safe workspace registry; it cannot
re-enable a denied workflow launcher.

The Flow binding is a validated invocation-result journal. The G4 Artifact set
and checkpoint remain the authoritative workflow state. The durable commit
order is:

1. execute the Agent and tools;
2. validate the exact output object;
3. commit the Flow binding;
4. commit G4 Artifacts;
5. persist the G4 checkpoint.

If a process stops after step 3, resume may reuse the validated binding and
complete steps 4-5 without rerunning tools.

## Program and Human adapter boundary

Program and Human remain leaf adapters because their semantics are not
equivalent to existing public Flow primitives.

A Program Step is not a direct `flow.exec()` call. Its adapter retains the
specialized Program Agent, compile/repair authorization, source and compiled
artifact provenance, workspace/argv/stdin restrictions, strict JSON Artifact
contract, separate stdout/stderr limits, and process-tree cleanup. Replacing
that adapter with `flow.exec()` would lose observable behavior.

A Human Step is not a `flow.call()` service. Its workspace adapter prepares the
question, raises a workflow control signal, commits the G4 checkpoint and
waiting request, returns control to the parent Session, and later resumes by
`run_id` / `request_id`. There is no equivalent Human/checkpoint primitive in
the public Flow API.

`workflow_execution` therefore sees Program and Human only through the generic
dispatcher boundary. Neither their leaf implementation nor their workspace
persistence belongs in the shared execution kernel.

## Stable Step-instance identity

A logical invocation identity includes:

```text
plan digest / Step ID / expansion path
```

For a non-foreach Step the expansion path is empty. For foreach it contains the
zero-based item index; future nested expansion appends another segment. The
retry attempt is recorded separately and does not change the logical result
binding.

The cache fingerprint includes the Agent configuration, normalized prompt and
inputs, output schema, allowed-tool set, and runner/adapter protocol version.
Changing any of those values invalidates an old result.

## Foreach language contract

`foreach_item(step, source) == item_binding` declares that `source` is an
Artifact whose runtime value must be a List, and that `step` is a template
expanded once for each member of that List.

Two Step-owned declarations complete the runtime contract:

```g4
foreach_concurrency(step) == 8;
foreach_errors(step) == errors;
```

`foreach_concurrency` is optional. When absent, the workflow-wide
`max_concurrency` is the only explicit concurrency limit. The effective number
of active iterations is bounded simultaneously by:

- the foreach-specific concurrency value, when present;
- workflow `max_concurrency`;
- available resource instances.

`foreach_errors` identifies the global aligned error Artifact. It is required
for an executable foreach Step so terminal item failures remain observable,
including for a zero-output Step.

## Foreach execution and aggregation

The source value must be a finite JSON List. Expansion creates logical
`step[index]` instances. Every instance receives the normal consumed global
Artifacts plus the local item binding. It uses the same executor dispatcher as
a non-foreach Step.

Each declared normal output Artifact becomes a List ordered by source index,
not completion order. Every aggregate output and the error Artifact have exactly
the source length:

- successful item: each output list stores its returned value and the aligned
  error entry is `null`;
- terminal failed item: every output list stores `null` and the aligned error
  entry stores a structured error record;
- empty source: every output and the error Artifact are empty Lists.

An error record contains at least `index`, `kind`, `message`, and `attempts`.
It does not include the raw item by default. Legitimate successful `null` output
is distinguishable because the aligned error entry remains `null`.

The collector publishes aggregate Artifacts only after every item is terminal.
Downstream graph operations continue normally even when some entries contain
collected errors.

## Per-iteration Step policy

Foreach itself does not own a second resource, timeout, or retry policy. Each
item is a normal Step instance and inherits:

- `resource_requirement`: acquired and released per attempt;
- `step_timeout`: applied per attempt;
- `max_attempts`: applied independently per item.

Resources are released before another attempt. If a caller configures retry
backoff, it must happen outside the lease. Cancellation is never retried. The
workflow timeout remains an outer bound over all iterations.
The shared retry and bounded indexed-parallel kernels drive these mechanisms;
the interpreter remains responsible for wrapping each attempt with admission,
resource leasing, timeout, validation, and checkpoint publication.

After an item exhausts its attempts, ordinary executor/validation/timeout
failures become the aligned error record. Workflow control and invariant
failures still abort or suspend the workflow:

- cancellation or workflow timeout;
- Human-input suspension;
- malformed graph, plan, checkpoint, or source type;
- checkpoint persistence failure;
- allocator invariant failure.

Outside foreach, a workspace Program keeps the existing
`$fusion_flow/program_error` error-valued Artifact compatibility behavior.
Inside foreach, that same reserved Program result is an iteration failure: it
participates in the Step's `max_attempts`, then contributes `null` normal
outputs and one compact aligned error after exhaustion. Raw captured
stdout/stderr are not copied into the foreach error record.

Agent- and Program-backed Steps are supported as foreach templates. A
Human-backed foreach fails during runner preflight in this version. The
existing Human resume document identifies only the base Step, not one expanded
iteration, and parallel Human iterations could otherwise race to publish
multiple active requests. Supporting it requires an iteration-aware request
queue and response checkpoint contract; it must not be approximated by
collecting a Human suspension as an ordinary item error.

## Partial checkpoint and resume

The checkpoint stores the exact source Artifact in its normal finite-JSON value
map and stores the terminal result of each item independently. Resume validates
that source plus the plan-bound Step/index identities, so a second redundant
source-digest field is unnecessary. A terminal result contains either validated
per-output values or the structured terminal error.

On resume:

- succeeded items are not invoked again;
- terminal failed items are not invoked again;
- pending items run;
- an item that was running during interruption returns to pending unless its
  validated Flow binding can be reused.

The aggregate Step is marked complete only after collection succeeds. A
checkpoint written after an individual item prevents already-terminal work from
being repeated even if collection or a sibling item is interrupted.

## Existing eager selection

The current `SelectNode` waits for its condition operands and both candidate
Artifacts, then copies one already-materialized value. Both candidate producers
remain executable. It is not lowered through `flow.if_()` and this change does
not alter its behavior.

## Compatibility and validation gates

The implementation is complete only when tests prove:

- where semantics overlap, public Flow and G4 paths exercise the same
  `RunContext`-free retry/indexed-traversal kernels without changing their
  distinct policies, while G4 exercises the graph-facing aggregation helper;
- the shared kernels work without an active `execution.run()` context;
- every Agent-owned grammar operator is consumed or rejected explicitly;
- the production `SessionRunner` honors the normalized Agent configuration;
- invalid Agent output is never committed to a Flow binding;
- foreach preserves input order under out-of-order completion;
- empty foreach produces empty output/error Lists;
- local and workflow concurrency limits compose;
- resource leases, timeout, and retry are per item;
- a terminal item failure is collected without cancelling siblings;
- cancellation and Human suspension are not collected as errors;
- Human-backed foreach is rejected before any item is dispatched;
- checkpoint resume invokes only unfinished items;
- existing eager select behavior remains unchanged.
