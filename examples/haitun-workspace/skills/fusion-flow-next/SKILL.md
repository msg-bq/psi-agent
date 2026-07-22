---
name: flow
description: Author FusionFlow workflow DSL from natural-language multi-agent tasks using grammar/FusionFlow.g4. Use for workflow orchestration, parallel or staged agent work, FusionFlow source, or G4 syntax. Generate FusionFlow DSL, never legacy .flow.ts TypeScript. Not for .prose files.
metadata: { "openclaw": { "emoji": "🐾", "homepage": "https://github.com/fuclaw" } }
---

# FusionFlow Authoring Skill

Turn a workflow-shaped request into FusionFlow source. The language contract is
`grammar/FusionFlow.g4`; read that file before authoring because it overrides every
summary and example in this document.

FusionFlow source is declarative. The LLM describes workflow identities, steps,
agents, artifacts, configuration, and data relations. The intended compiler pipeline
parses and checks that source before lowering it to TypeScript. **Never generate
TypeScript, imports, `flow.*` calls, or `run(...)` by hand.** Legacy `.flow.ts`
authoring remains the job of the sibling `fusion-flow` skill during migration.

**Current implementation boundary:** `src/parser.ts`, `src/checker.ts`, and
`src/generator.ts` are stubs that throw. Until real implementations are available,
this skill is syntax-authoring only: validate manually against `FusionFlow.g4`, do
not call the stubs, and do not claim compiler validation, TypeScript generation, or
execution.

## When to activate

Activate when the user:

- asks to build or edit a FusionFlow workflow;
- describes multi-agent collaboration, parallel review, fan-out/fan-in, a pipeline,
  iterative work, conditional selection, scoring, or role-based coordination;
- asks about `FusionFlow.g4`, its DSL, its preset operators, or a FusionFlow source
  file.

Do not activate for `.prose` files or for maintaining a legacy `.flow.ts` program.

### Multi-agent requests become workflows

When a task is workflow-shaped, author a FusionFlow workflow instead of role-playing
all agents in one reply. Skip workflow authoring only when the user explicitly asks
for a one-off answer rather than a workflow asset.

## Authoring protocol

1. Restate the intended workflow in one sentence. Ask at most one question if a
   missing detail changes the structure materially.
2. List the required functions internally: external inputs/outputs, steps, agent
   assignments, data dependencies, concurrency, conditions, retries, and limits.
3. Map every required function to syntax that actually exists in
   `grammar/FusionFlow.g4` and to a catalog operator. If a function has no mapping,
   report the missing capability and stop; never invent a keyword or operator.
4. Generate exactly one FusionFlow source. Use the caller's target path. If the
   integration has not defined a filename or extension, return one fenced
   `fusionflow` block and let the integration choose its storage path.
5. When a real parser/checker is available, run it before claiming validity and
   surface diagnostics in source order. With the current stubs, validate manually
   against the G4 and state that the source was not compiler-validated.
6. Do not compile or run the source unless the workspace exposes a FusionFlow
   compiler/runner and the user asked for execution. Never claim that a workflow ran
   based only on successful authoring.

One intent produces one real source file. Do not create mock, offline, simplified,
backup, or generated-TypeScript twins.

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
  `false`, and `FALSE`; prefer `True` and `False` for generated source.
- Line comments start with `--`; block comments use `/* ... */`.

The grammar fixes the shape of `if(...)`, but ordinary preset and catalog operators
share a flexible call rule. Flexible syntax does not mean arbitrary arity: the
checker/catalog validates operator names, arity, concepts, value constraints,
workflow legality, and exact backend support.

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
  first argument. Current exact TypeScript lowering may reject these declarations
  with design reference `S01`; preserve the user's meaning and surface the checker
  diagnostic rather than approximating it.
- `Instruction`, `StepName`, and similar concepts currently hold catalog identities,
  not free-form text. Map natural-language prompts to catalog-provided identities;
  if none exists, report that the instruction cannot be represented without losing
  meaning.
- Content-based scoring or selection requires catalog operators that produce the
  compared value. `if(...)` only selects between terms; it does not inspect an
  artifact or invent a score. Stop when the required catalog operator is missing.
- Execution order, dependency collection, branch evaluation, retries, and timeouts
  belong to lowering/runtime. Do not claim runtime behavior the checker or runner has
  not confirmed.
- Variables, quantifiers, truth formulas, theories, rules, implications,
  biconditionals, query/SAT/optimization requests, local concept declarations, and
  local operator declarations are outside this language surface.

## Canonical example

This example shows two independent reviewers feeding one synthesizer. It demonstrates
syntax, not proof of catalog compatibility or backend support.

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

Before presenting or saving generated source, verify:

- only supported global `const` declarations precede the workflows;
- there is at least one workflow, with a lowercase name;
- every workflow item is `term == term;`;
- formula comparisons use `=`, while top-level assertions use `==`;
- every `if(...)` has one formula and two value terms;
- every preset operator uses the documented arity and concept-compatible values;
- all referenced catalog operators are known rather than invented;
- every input, output, step, executor, and intermediate artifact required by the
  plan is represented;
- no TypeScript, imports, `flow.*` primitives, or `run(...)` calls appear;
- compiler/checker diagnostics are reported instead of hidden or approximated.

## User-facing response

Lead with the workflow result, not implementation jargon. Mention the DSL file or
grammar only when the user asks for technical detail. If validation or execution is
blocked, state the exact boundary plainly; never substitute a fabricated result.
