---
name: flow
description: For authoring and running FusionFlow multi-agent workflows. Use when the task involves FusionFlow source, an explicit mention of "FusionFlow"/"agent-flow"/"Fuclaw", or a request to coordinate multiple agents, run sub-tasks in parallel, build a multi-step pipeline, or inspect a prior workflow run. Not for `.prose` files. Activated by task intent, not by slash commands.
metadata: { "openclaw": { "emoji": "🐾", "homepage": "https://github.com/fuclaw" } }
---

# FusionFlow Skill (Fuclaw)

This skill is the author + run protocol for **FusionFlow** (Fuclaw): author declarative workflow source from natural language, run it with the workspace runtime, and read the full **execution graph** for replay. Unlike OpenProse, where the LLM *is* the VM, FusionFlow execution belongs to the runtime; the LLM authors the workflow, starts the run, and explains its artifacts.

> **What you're working in.** The normal delivery is a **self-contained bundle**. Call its root `<workDir>`. Authored FusionFlow source and `runs/` artifacts live relative to that directory. In the psi-agent workspace, task workflows live under the workspace `flows/<task-slug>/` tree and are run through `flow_run`; in another client, use the runner exposed by that bundle. Do not expose internal execution files to the user.

> **No slash commands.** This skill is triggered by **natural-language intent**, never by a `/flow xxx` command. The user just talks: "帮我写个并行调研的工作流" / "跑一下刚生成的那个" / "刚才那个跑完了吗". Do NOT teach, suggest, or expect any `/flow run` / `/flow show` / `/flow author` syntax — those slash commands do not exist and printing them to the user is a bug (a user in an environment without this skill installed will see "命令没找到"). Map what the user *means* to the actions below.

## When to Activate

Activate this skill when the user:

- Asks to run a FusionFlow source file they already have — e.g. one you just authored in Authoring Mode, or a file they point you at ("跑一下这个 / 帮我跑 / 执行"). This skill does **not** ship runnable demo examples; "run" always means a concrete workflow the user has.
- Asks to see the result of a previous run ("跑完了吗 / 看看结果 / 上次那个怎么样了")
- Mentions "agent-flow", "Fuclaw", or "@agent-flow/core"
- **Describes any task that needs a multi-agent workflow or agent collaboration**, even without saying "flow" — e.g. "让几个 agent 分别审一遍再汇总", "并行跑 N 个子任务再合并", "一步接一步处理(先 A 再 B 再 C)", "多角度评审 / 打分选边", "把这件事拆成多个 agent 协作". If the task clearly benefits from orchestrating more than one agent / parallel branches / a multi-step pipeline, enter **Authoring Mode** (below) and offer to build a flow.

When in doubt about whether a task is "workflow-shaped": if it would take **two or more coordinated LLM steps** (fan-out, pipeline, loop, or judge-then-branch), it qualifies — activate and propose a flow. A single one-shot question does not.

### HARD RULE: when you recognize a multi-agent task, your job is to BUILD A FLOW — not to do it yourself

Once a task is workflow-shaped (multiple agents / parallel branches / multi-step pipeline / judge-then-branch), your **one default action** is to enter Authoring Mode and build a FusionFlow workflow. That is the entire point of this skill — the runtime spawns and coordinates the sub-agents; **you do not play those sub-agents yourself**.

Do **NOT** offer "我直接帮你做这一次" as an option, and especially do **NOT** make it the default. Building the flow IS how you help — there is no faster "just do it manually" path that's better; doing it by hand throws away the runtime (parallelism, the execution graph, replay, the reusable artifact) and contradicts "one intent = one authored workflow".

❌ **Real failure to never repeat** (observed in testing): user said "让几个 AI 从安全/性能/可读性分别审一段代码再汇总". The agent replied with "方式 A：我直接帮你审这次代码 / 方式 B：给你做成可复用工作流" — offering to personally act as the three reviewers, with the manual path listed first as the default. **Wrong.** The correct response is to go straight into Authoring Mode and build the review workflow (three reviewer steps produce separate artifacts; one synthesizer step consumes them). No A/B menu, no "I'll just review it myself".

✅ **Correct shape**: "🐾 这是个多 agent 协作任务，我来帮你搭一个工作流：3 个审查 agent（安全/性能/可读性）并行审 → 一个汇总 agent 合并成带严重等级的报告。" Then run the author loop (understand → model → map to G4 → author → validate → one heads-up line → **run it**).

The only time you don't build a flow is when the user **explicitly** says they just want a one-off answer and not a tool ("别给我搭工具，就这一次，你直接说结论"). Even then, confirm — don't assume.

Do **not** activate this skill for `.prose` files — those belong to OpenProse.

## Architectural Difference vs OpenProse

| Aspect | OpenProse | OpenFlow (Fuclaw) |
| --- | --- | --- |
| VM substrate | LLM session simulating prose.md | FusionFlow runtime |
| Program format | `.prose` markdown DSL | FusionFlow DSL defined by `grammar/FusionFlow.g4` |
| Sub-agent spawn | OpenClaw `sessions_spawn` | `@agent-flow/core` shelling out to an external agent CLI (claude / openclaw / hermes / psi) |
| State directory | `.prose/runs/<id>/` | `<workDir>/runs/<id>/` |
| Replay artifact | `bindings/*.md` + `state.md` | `bindings/` + `trace/` + **`execution-graph.json`** |
| Control flow | Prose VM keywords | Artifact dependencies, workflow/step assertions, `foreach_item`, and `if(...)` |

The skill's job is to:

1. Author or resolve the user's FusionFlow source.
2. Start it through the workspace's FusionFlow runner.
3. Surface the resulting `runs/<id>/` and explain the execution graph.

## Intent Routing

The user talks in natural language. Map what they **mean** to one of these actions. There is **no slash-command syntax** — never echo a `/flow xxx` form back at them.

| What the user says (examples) | Action |
| --- | --- |
| "我能用这个干嘛 / 你能帮我做什么" | Describe capabilities in plain language (see "Capabilities" at the bottom) + offer to build a flow |
| "跑一下这个 / 帮我跑 X / 执行这个工作流" | Run the FusionFlow source the user already has (e.g. one you just authored in Authoring Mode), then surface the result. **This skill does not ship runnable demo examples** — the only thing you run is a workflow the user points at or that author just produced. |
| "接着上次那个跑 / 只重跑改动的部分" | (v0.6) Re-run reusing the old `runs/<runId>/`; cached bindings skip the LLM. See "Resume" section |
| "看看结果 / 刚才那个跑完了吗 / 上次跑得怎么样" | Read `<workDir>/runs/<runId>/execution-graph.json` (or the most recent run) and walk the user through it |
| "环境齐不齐 / 能不能跑 / 帮我检查下" | Verify the FusionFlow runner, configured engine CLI, and authoring readiness (`<workDir>` has `node_modules`); run `npm run doctor` if present |
| **"帮我写个工作流做 X / 帮我编排 / 我想让几个 agent ..."** | **Author a new FusionFlow workflow from natural language. See "Authoring Mode" below.** |
| Anything else workflow-shaped | Interpret intent against this table |

## Running a Program

Use the FusionFlow runner exposed by the current workspace. In psi-agent:

1. `flow_run(action="start", flow_path=...)`
2. Poll with `flow_run(action="status", run_token=...)`.
3. When done, call `flow_run(action="result", run_token=...)`.

In another client, use the runner supplied by that FusionFlow bundle. Do not invoke internal implementation files directly.

`<workDir>` is **the directory the user is working in**. How to resolve it:

1. **psi-agent workspace:** use the workspace root containing `skills/fusion-flow-next/` and `flows/`. Authored task workflows go under `flows/<task-slug>/`; artifacts land under `runs/`.
2. **Standalone bundle:** use the folder containing `grammar/FusionFlow.g4` and the FusionFlow runner. Authored workflows go under its `examples/`; artifacts land under `runs/`.
3. **If you genuinely can't tell which folder to work in** (e.g. several candidates), ask the user once in plain language: "你把 fusion-flow 文件夹拷到哪了？我在那个目录里帮你跑。" Then **remember it for the rest of this session** — don't re-ask.

Never guess a path without verification. Never hardcode a machine-specific path. Don't scan the filesystem for another copy — work in the folder the user is actually using (see Hard-stop #4 in Authoring Mode).

Pass runtime input overrides through the runner's supported input interface. Do not edit the workflow to bake in one run's values.

After the run, the runner returns two values you must capture:

```
[run] <runId>
[run] dir: <abs-path-to-runs/runId>
```

Use that `runId` to walk the user through the run (see "Reading a Run").

### Resume (`--resume`) — v0.6

If a run blew up halfway, or the user wants to re-execute only the parts whose inputs changed, pass `--resume=<runId>` (or `last`) through the FusionFlow runner.

How it behaves:

- The same `runDir` is reused — no new `runs/<id>/` directory is created.
- For each completed node, the runtime records an input hash over its effective configuration and inputs.
- If `bindings/<name>.md` exists **and** the meta's `inputHash` matches, the LLM call is skipped — the cached content is returned, and the graph node is marked `cached: true`.
- If the user changed an instruction, model, input, or upstream result, that node and its downstream dependents re-run.
- Old runs from before v0.6 don't have `inputHash` in their meta. `--resume` falls back to lenient mode: name-only match. After the first re-run, those bindings get hashes written and become strict.

When recommending a resume run to the user, surface what will be reused vs re-run by reading the existing `bindings/*.meta.json` files first — never promise "everything cached" without checking.

Caveats to mention if asked:

- Code-backed step implementation changes may be invisible to the input hash. If one changes, rename the step or clear its cached binding before resuming.
- Tokens reported in `meta.json` only count *new* calls. Total cost across the original + resume is the sum of both runs' meta.

## Running an LLM Flow: Pre-flight

Before executing a FusionFlow workflow with agent steps:

1. Internally estimate cost/latency from the flow's node count (each LLM call is a CLI subprocess, ~3-10s each; a fan-out with N reviewer sessions ≈ N calls). Fold that into the single plain-language heads-up line ("预计几分钟") — don't dump the per-node math on the user.
2. Say the one heads-up line, then **run — do not ask "要不要跑" or wait for approval.** The user already asked for the task; building + running the flow is how you do it. (Only exception: they explicitly said "只生成别跑".)

Only perform environment-readiness checks when the user explicitly asks for them; follow [Doctor Checks](#doctor-checks).

### Running is the runtime's job, not yours

When the user asks to run a workflow, your ENTIRE job is: resolve `<workDir>`, invoke its FusionFlow runner once, then report what the runtime returned. The runtime owns subprocesses and environment setup. **You do not pre-flight the subprocess environment.** Specifically, before running:

- Do NOT check whether `uv` / `python` / `claude` is "on PATH" in your shell. Your PATH is not the runtime's PATH. A missing binary in your shell does NOT mean the flow will fail.
- Do NOT `pip install` / `npm install` / modify PATH to "fix" a tool you think is missing.
- Do NOT inspect or second-guess a step's external command. Run the workflow as-is and let the runtime resolve it.
- Do NOT run ad-hoc interactive probes such as bare `node`, bare `python`, or bare `npx`. They can open a REPL/prompt and appear to hang.

Just run the flow. If it actually fails, then go to "When a run fails".

### A flow run is long — never let a timeout kill it

A FusionFlow workflow is not a quick shell command. Agent steps have cold-start latency, and a parallel or multi-step workflow can take minutes. Two hard rules:

1. **If your client exposes a background/long-running run tool, use it — do NOT run the workflow through a foreground shell with a short timeout.** In psi-agent, `flow_run` is the required path: start, poll status, then fetch the result.
2. **If no background run tool exists**, use the official FusionFlow runner with the longest supported timeout. Read fresh `runs/<runId>/progress.jsonl` entries to report progress; do not assume a silent run is stuck.

### When a run fails

A non-zero exit or runtime failure is a **STOP-and-report point**. Do exactly these three steps, in order, then stop:

1. Report the exit code, the `runId`, and the error tail the runtime already printed.
2. Read AT MOST two files to explain it: `runs/<runId>/meta.json` and the failed node's `bindings/<name>.md`.
3. State your single best hypothesis, then **STOP and hand back to the user. End your turn.**

These actions are FORBIDDEN when a run fails. If you find yourself about to do any of them, STOP — you are drifting:

- ❌ Editing the workflow, or creating a `-modified` / `-quick` / `.bak` copy to work around the failure.
- ❌ Running the wrapped command yourself (`uv run ...`, `python -m ...`, `python -c ...`) "to see what happens".
- ❌ Launching probe processes, trial flags, kill-and-retry loops, or any multi-minute autonomous debug session.
- ❌ `pip install` / `npm install` / editing PATH / env to "fix" the environment.

The user did NOT ask for an autonomous debug session — they asked you to run a file and report. After reporting the failure, **STOP and hand back**. Do NOT create or run a `*-offline` / mock version of the failing flow "to show the skeleton works" — a mock with baked-in output is a forgery, not a proof (see the global no-mock rule below). If you think a deeper check is worth it, propose it as a single command and let the user decide.

### Don't fake or guess progress

While a run is in flight, your only sources of truth are the runtime's stdout and the files it writes under `runs/<runId>/`. Do NOT infer progress by scanning the external tool's output directory and guessing — timestamps on pre-existing files (e.g. a prior run's artifacts) will mislead you into reporting "it's processing" when nothing new is happening. If you can't see fresh runtime output, say "no new output yet", not a fabricated status.

## Reading a Run

When the user wants to see a run's result ("跑完了吗 / 看看结果"), perform these reads in parallel (resolve the target `runId`, or pick the most recent `<workDir>/runs/*/` if they said "上次 / last"):

- `<workDir>/runs/<runId>/meta.json` — top-level status, durations, call counts
- `<workDir>/runs/<runId>/execution-graph.json` — the tree
- `<workDir>/runs/<runId>/bindings/` — list filenames; read `final.md` if present
- `<workDir>/runs/<runId>/trace/*.json` — only on demand (these are large)

Then summarize for the user. **Default (non-technical user): keep it short and friendly** — lead with the result, not the metrics:

1. **一句话结果** — 跑成功了没 + 大概多久，e.g. "🎉 跑完啦，用了约 40 秒。" Don't open with token counts or agent counts.
2. **产出** — point them at the final answer: read `bindings/final.md` (or the most relevant binding) and show *that*, not the graph.
3. **出问题才说细节** — only if a node failed: say which step and your one best hypothesis.

**Developer / on-demand:** if the user asks "用了多少 token / 给我看执行图 / 哪几步" then show the technical verdict line — `ok in 12.3s, 4 agents, 18.2k input tokens, 2.1k output tokens` (read from `meta.json` → `totalTokens`/`llmCalls`/`durationMs`) + graph shape (node `type` tree) + per-branch results. Never dump the full JSON; be a curator.

## File Locations

Paths below are relative to `<workDir>`:

| File | Location | Purpose |
| --- | --- | --- |
| language contract | `skills/fusion-flow-next/grammar/FusionFlow.g4` in a workspace, or `grammar/FusionFlow.g4` in a bundle | Authoring syntax source of truth |
| workflow source | workspace: `flows/<task-slug>/<task-slug>.flow`; bundle: `<workDir>/examples/flow-author-<id>.flow` | One authored workflow per intent |
| `<workDir>/runs/<runId>/` | created by each run | Per-run artifacts (graph, bindings, trace) |
| `<workDir>/.env` | user responsibility (optional) | FLOW_ENGINE selection + optional ANTHROPIC_* passthrough for claude engine + FLOW_PSI_* for psi-agent |

## Authoring Mode

Turn a natural-language intent into one runnable FusionFlow workflow. The user describes the result they want; you author declarative source defined by `grammar/FusionFlow.g4`, validate it through the workspace runner, and run it. Internal execution artifacts are not part of the user conversation.

> **NO-MOCK RULE.** One intent produces exactly one real workflow. Never fabricate an offline, simplified, backup, test-harness, or hard-coded twin. Validation checks the real source; the result comes from the real run.

### When to enter Authoring Mode

- The user asks to build or edit a FusionFlow workflow.
- The user describes two or more coordinated agents, parallel branches, a staged pipeline, iteration, scoring, selection, or role-based collaboration.
- The user asks for a workflow-shaped task without naming FusionFlow.

Skip authoring only when the user explicitly asks for a one-off answer rather than a workflow.

### The 5-step author loop

1. **Understand intent** — restate the goal in one sentence. Ask at most one question when a missing detail materially changes the workflow.
2. **Model the workflow** — identify external inputs/outputs, steps, agents, artifacts, data dependencies, concurrency, conditions, retries, and limits.
3. **Map every function to real syntax** — read `grammar/FusionFlow.g4`, use only its constructs and proven catalog operators, and stop with a concrete missing-capability warning when an exact mapping does not exist.
4. **Author exactly one source** — use the caller's target path; otherwise use `flows/<task-slug>/<task-slug>.flow` in the psi-agent workspace or `<workDir>/examples/flow-author-<YYYYMMDD>-<NNN>.flow` in a standalone bundle.
5. **Validate and run** — use the FusionFlow runner. Fix real source diagnostics for at most three rounds. Once valid, say one friendly heads-up line and start the run immediately. Stop after validation only when the user explicitly said not to execute.

Never tell a non-technical user about source paths or internal execution artifacts. Describe the business workflow instead.

### Talking to the user while you work

| Phase | User-facing example |
| --- | --- |
| Planning | `🐾 正在帮你规划…` |
| Ready to run | `🚀 方案定了，正在帮你跑，预计几分钟…` |
| Parallel work | `⏳ 3 个子任务同时进行中…` |
| A step finishes | `✅ 「安全审查」完成` |
| Complete | `🎉 跑完啦，结果在下面` |

Send one short line at meaningful phase changes. Do not paste runtime logs, source paths, operator names, token counts, or execution graphs unless asked. Always send the ready-to-run line before starting a cold agent process.

### Hard stops in Authoring Mode

1. Do not fake a result instead of running the workflow.
2. Do not write or run more than one workflow for one intent.
3. Do not report numbers or conclusions that did not come from the current real run.
4. Do not work outside the resolved `<workDir>` or workspace `flows/` tree.
5. Do not invent syntax, operators, concepts, or catalog identities to approximate an unsupported requirement.

### Heads-up line

For a non-technical user, use one sentence explaining the outcome and rough time, then run:

```text
🚀 我来帮你做：<一句话说明最终产出>，预计几分钟，这就开始。
```

Do not turn this into an approval gate. Technical structure is shown only when a developer explicitly asks.

## Surface syntax

### File and declarations

```text
(const declaration;)*
workflow block+
```

- A file contains zero or more global `const` declarations followed by one or more
  workflows.
- Constants attach concrete identities to catalog concepts:

  ```text
  const artifact_name: Artifact;
  const worker: Agent, Executor;
  ```

- Constant and workflow names are lowercase identifiers. Concept names begin with
  an uppercase letter.
- Quoted constants are restricted IDs, not strings. They may contain only
  `A-Z a-z 0-9 . ! # $ % ? @ _ { | } ~ \`` and cannot contain whitespace or escape
  sequences. Prefer declared lowercase constants for instructions and other named
  values.
- Source files cannot declare concepts or operator signatures; those come from the
  external catalog.

### Workflow blocks and assertions

```text
workflow workflow_name {
  operator(arguments) == value;
}
```

- Workflow blocks contain assertions only, and every assertion ends with `;`.
- Top-level assertion equality is `==`.
- Numeric/formula equality is `=`. Other formula comparisons are `!=`, `<`, `<=`,
  `>`, and `>=`.
- Do not interchange `==` and `=`.

### Terms, formulas, and lists

Terms may be operator calls, list literals, numbers, booleans, constants,
parenthesized terms, arithmetic, or `if(...)` expressions.

- Arithmetic precedence, high to low: unary `+`/`-`; right-associative `^`; `*` `/`
  `%`; then `+` `-`.
- Formula precedence, high to low: `!`, `AND`, then `OR`; parentheses override it.
- `AND`/`and`/`&` and `OR`/`or`/`|` are accepted aliases.
- A bare term is not a formula. Conditions bottom out at comparisons.
- `if(condition, then_term, else_term)` is value-producing and always has exactly
  three arguments. Use nested `if` expressions for N-way choice.
- Lists are ordinary ordered terms: `[item_a, item_b]`. All four `*_multi` operators
  return Lists.
- Boolean spellings accepted by the grammar are `True`, `true`, `TRUE`, `False`,
  `false`, and `FALSE`; prefer `True` and `False` in authored source.
- Line comments start with `--`; block comments use `/* ... */`.

The grammar fixes the shape of `if(...)`, but ordinary preset and catalog operators
share a flexible call rule. Flexible syntax does not mean arbitrary arity: the
runtime validates operator names, arity, concepts, value constraints, and workflow
legality before execution.

## Preset operator catalog

Use these exact names and signatures. External catalog operators may also be used
when the workspace proves they exist.

### Workflow owner

| Operator | Signature | Arity |
| --- | --- | ---: |
| `input_workflow` | `(Workflow, Artifact) -> Bool` | 2 |
| `input_workflow_multi` | `(Workflow) -> List` | 1 |
| `output_workflow` | `(Workflow, Artifact) -> Bool` | 2 |
| `output_workflow_multi` | `(Workflow) -> List` | 1 |
| `max_concurrency` | `(Workflow) -> Integer` | 1 |
| `workflow_timeout` | `(Workflow) -> Integer` | 1 |

### Step owner

| Operator | Signature | Arity |
| --- | --- | ---: |
| `step_name` | `(Step) -> StepName` | 1 |
| `step_instruction` | `(Step) -> Instruction` | 1 |
| `step_executor` | `(Step) -> Executor` | 1 |
| `step_timeout` | `(Step) -> Integer` | 1 |
| `max_attempts` | `(Step) -> Integer` | 1 |

### Data, loop, and resource owner

| Operator | Signature | Arity |
| --- | --- | ---: |
| `consumes` | `(Step, Artifact) -> Bool` | 2 |
| `consumes_multi` | `(Step) -> List` | 1 |
| `produces` | `(Step, Artifact) -> Bool` | 2 |
| `produces_multi` | `(Step) -> List` | 1 |
| `foreach_item` | `(Step, List) -> Artifact` | 2 |
| `resource_requirement` | `(Step, Resource) -> Integer` | 2 |

### Agent owner

| Operator | Signature | Arity |
| --- | --- | ---: |
| `agent_config` | `(Agent, Model, Engine, ApiBase) -> Bool` | 4 |
| `allowed_tool` | `(Agent, Tool) -> Bool` | 2 |
| `max_output_tokens` | `(Agent) -> Integer` | 1 |
| `temperature` | `(Agent) -> ComplexNumber` | 1 |
| `reasoning_effort` | `(Agent) -> ReasoningEffort` | 1 |
| `max_turns` | `(Agent) -> Integer` | 1 |

## Modeling rules

- Model sequencing and fan-out/fan-in through artifact relations. Producers and
  consumers define dependencies; do not invent imperative `parallel`, `pipeline`, or
  block syntax.
- `max_concurrency(workflow)` configures workflow-level concurrency.
- `foreach_item(step, list)` models a step applied across a List. Do not invent loop
  variables or loop blocks.
- `if(...)` selects a value. It is not a Step, block, or preset operator.
- `input_workflow` and `output_workflow` use the enclosing workflow name as their
  first argument.
- `Instruction`, `StepName`, and similar concepts are catalog identities rather than
  free-form text. Map natural-language prompts to catalog-provided identities; if no
  exact identity exists, report the missing capability instead of inventing one.
- Content-based scoring or selection requires catalog operators that produce the
  compared value. `if(...)` only selects between terms; it does not inspect an
  artifact or invent a score. Stop when the required catalog operator is missing.
- Execution order, dependency collection, branch evaluation, retries, and timeouts
  belong to the runtime. Do not promise behavior the runner has not confirmed.
- Variables, quantifiers, truth formulas, theories, rules, implications,
  biconditionals, query/SAT/optimization requests, local concept declarations, and
  local operator declarations are outside this language surface.

## Canonical example

This example shows two independent reviewers feeding one synthesizer.

```fusionflow
const request: Artifact;
const review_a: Artifact;
const review_b: Artifact;
const final_report: Artifact;

const reviewer_a: Step;
const reviewer_b: Step;
const synthesize: Step;

const reviewer_a_name: StepName;
const reviewer_b_name: StepName;
const synthesize_name: StepName;
const review_instruction: Instruction;
const synthesis_instruction: Instruction;

const analyst_a: Agent, Executor;
const analyst_b: Agent, Executor;
const editor: Agent, Executor;
const model: Model;
const engine: Engine;
const api: ApiBase;

workflow review_pipeline {
  input_workflow(review_pipeline, request) == True;
  output_workflow(review_pipeline, final_report) == True;
  max_concurrency(review_pipeline) == 2;

  step_name(reviewer_a) == reviewer_a_name;
  step_instruction(reviewer_a) == review_instruction;
  step_executor(reviewer_a) == analyst_a;
  consumes(reviewer_a, request) == True;
  produces(reviewer_a, review_a) == True;

  step_name(reviewer_b) == reviewer_b_name;
  step_instruction(reviewer_b) == review_instruction;
  step_executor(reviewer_b) == analyst_b;
  consumes(reviewer_b, request) == True;
  produces(reviewer_b, review_b) == True;

  step_name(synthesize) == synthesize_name;
  step_instruction(synthesize) == synthesis_instruction;
  step_executor(synthesize) == editor;
  consumes_multi(synthesize) == [review_a, review_b];
  produces(synthesize, final_report) == True;

  agent_config(analyst_a, model, engine, api) == True;
  agent_config(analyst_b, model, engine, api) == True;
  agent_config(editor, model, engine, api) == True;
}
```

## Validation checklist

Before presenting or saving source, verify:

- only supported global `const` declarations precede the workflows;
- there is at least one workflow, with a lowercase name;
- every workflow item is `term == term;`;
- formula comparisons use `=`, while top-level assertions use `==`;
- every `if(...)` has one formula and two value terms;
- every preset operator uses the documented arity and concept-compatible values;
- all referenced catalog operators are known rather than invented;
- every input, output, step, executor, and intermediate artifact required by the
  plan is represented;
- only syntax defined by `FusionFlow.g4` and proven catalog operators appears;
- validation diagnostics are reported instead of hidden or approximated.

### Running it

After validation, run the same source through the FusionFlow runner. Capture the `runId`, monitor real progress, and report the final binding in plain language. If the runner fails, use the stop-and-report protocol above rather than rewriting the workflow behind the user's back.

### What Authoring Mode is NOT

- It does not guarantee good domain content; agent instructions still need the user's domain context.
- It does not invent missing language or catalog capabilities.
- It does not stop after handing the user a file unless they explicitly asked for authoring only.
- It does not expose internal execution artifacts as part of the user experience.

## Doctor Checks

When the user asks to check their environment ("环境齐不齐 / 能不能跑"): in the bundle, the quickest path is `cd <workDir> && npm run doctor` (the bundle ships a `doctor.mjs`). Prefer that over hand-written shell checks.

All manual checks must be non-interactive and bounded. Never run a command that can wait for user input, especially bare `node`, bare `python`, bare `npx`, or package-install fallbacks such as `npx tsc` after dependencies are missing.

If `npm run doctor` is not present, check manually:

```bash
command -v node && node --version        # need >= 20; never run bare `node`
test -f <workDir>/.env                   # optional in v0.7 (FLOW_ENGINE config); the engine CLI's own auth is what matters
test -d <workDir>/node_modules           # must exist; if missing, report "run npm install in <workDir>" and stop
claude --version                         # the configured FLOW_ENGINE CLI must be on PATH (default: claude)
```

Report each as ✓ / ✗. Never echo any API key value. In v0.7 `<workDir>/.env` no longer holds an LLM-direct key — auth is the engine CLI's own config (the claude engine will passthrough `ANTHROPIC_*` from the shell environment if present, else use claude's own login).

### Authoring readiness

Authoring is ready when `grammar/FusionFlow.g4` is readable, the required catalog is loaded, the runner accepts and validates the target source, and the configured agent engine is available.

If validation fails, report the first diagnostics in source order and do not run. Otherwise report:

```
✓ FusionFlow authoring and runner ready
```
### Engine readiness (v0.7)

Agent steps use the configured external CLI (`FLOW_ENGINE`, default `claude`). Check only that engine's CLI; non-agent steps need no engine pre-flight.

```bash
claude --version                                    # if FLOW_ENGINE=claude (default)
psi-agent run --help                                # if FLOW_ENGINE=psi
# Windows only: git-bash must exist for the claude CLI
test -f /c/Program\ Files/Git/bin/bash.exe || \
  test -f /d/Program\ Files/Git/bin/bash.exe       # one of the candidates
```

For the psi-agent engine, configure its workspace and profile directly:

```bash
FLOW_ENGINE=psi
FLOW_PSI_WORKSPACE=/abs/path/to/psi-agent/workspace
FLOW_PSI_PROFILE=fusion
# Optional:
FLOW_PSI_CONFIG=/abs/path/to/config.toml
FLOW_PSI_AI_SOCKET=http://127.0.0.1:9000/v1
```
Keep provider URLs and API keys in psi-agent's own profile config, not in this Fuclaw/OpenProse `.env`. `FLOW_PSI_AI` / `FLOW_PSI_MODEL` / `FLOW_PSI_BASE_URL` / `FLOW_PSI_API_KEY` exist only as temporary overrides for local debugging.

If the engine CLI is missing:

```
✗ FLOW_ENGINE=claude not ready
  Install Claude Code from https://docs.claude.com/en/docs/claude-code, or set FLOW_ENGINE to an installed CLI (openclaw / hermes / psi).
```

If on Windows and no git-bash found in any candidate path, the runtime will best-effort probe at call time and surface a clear error. Doctor reports:

```
⚠️ claude engine may fail on Windows: no git-bash found in default paths.
  Set CLAUDE_CODE_GIT_BASH_PATH to your bash.exe location, or install Git for Windows.
```

## Capabilities

When the user asks what this skill can do, answer in plain language and never teach slash commands:

```text
🐾 FusionFlow
用自然语言驱动多 agent 工作流，带完整执行图回放。直接跟我说就行：

  • "帮我写个工作流做 X / 帮我编排 ..."       → 我把需求编排成真实工作流并直接运行
  • "跑一下刚生成的那个 / 帮我跑这个工作流"   → 执行你指定的工作流并返回真实结果
  • "接着上次那个跑 / 只重跑改动的部分"       → 复用未变化的步骤，只重跑受影响部分
  • "刚才那个跑完了吗 / 看看上次结果"         → 读取实际运行记录并解释产出
  • "环境齐不齐 / 能不能跑"                    → 检查语言、runner 和 agent engine 是否就绪

不附带现成 demo；你描述目标，我现场编排。
```

## Security + Approvals

FusionFlow source is declarative, but a run may invoke agents, tools, and external commands with the runner's permissions. Inspect any user-supplied workflow before its first execution, preserve existing approval requirements for side effects, and refuse to execute a workflow directly from a remote URL. Never include credentials in workflow source or run artifacts.
