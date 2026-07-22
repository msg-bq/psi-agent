# FusionFlow Next Python Migration Design

## Goal

Replace the inactive FusionFlow Next compiler implementation with Python while
preserving the current DSL, Core IR, diagnostics, phase boundaries, and final
TypeScript runtime target.

The existing `fusion-flow` runtime remains unchanged and active. FusionFlow Next
remains inactive until its parser, checker, generator, planning check, and
integration path are complete.

## Current State

Pull requests #1 through #3 are merged and establish a TypeScript scaffold, the
current `FusionFlow.g4`, and a minimal Workflow Core IR. Pull requests #4 and #5
are open drafts containing a TypeScript parser and compiler scaffold.

The migration starts from current `main`. It does not rewrite merged history.
Python replacement pull requests will be stacked, and the old #4 and #5 drafts
will be closed only after their Python equivalents pass the agreed checks.

## Sources of Truth

The committed `examples/haitun-workspace/skills/fusion-flow-next/grammar/FusionFlow.g4`
is the language source of truth. The uncommitted `Workflow.g4` in the reference
KEDispatcher checkout is broader in several places and must not replace it.

The KEDispatcher checkout is a read-only implementation reference for:

- Python ANTLR lexer/parser integration;
- handwritten parse-tree visitor dispatch;
- parse-local concept, constant, and operator resolution;
- Python Core IR naming and construction patterns.

FusionFlow Next copies only the behavior required by its current grammar. It
does not import KEDispatcher at runtime or copy its variables, quantifiers,
rules, theories, requests, registries, execution callbacks, or global singleton
state.

## Compiler Pipeline

```text
FusionFlow DSL source
  -> ANTLR-generated Python lexer/parser
  -> handwritten Python Core IR visitor
  -> WorkflowFile / Workflow Core IR
  -> Python static checker
  -> Python TypeScript generator
  -> unchanged FusionFlow TypeScript runtime
```

The parser owns syntax diagnostics and lossless parse-tree lowering. The
checker owns operator/catalog semantics and exact-lowering eligibility. The
generator consumes checked IR and emits deterministic TypeScript. None of these
phases executes a workflow.

## Python Layout

The replacement stays self-contained under the existing skill directory:

```text
examples/haitun-workspace/skills/fusion-flow-next/
  fusion_flow_next/
    __init__.py
    contracts.py
    core_ir.py
    parser.py
    checker.py
    generator.py
    planning.py
    generated/
  grammar/FusionFlow.g4
  test/
```

The repository's existing Python environment supplies tests and linting. Add
only the ANTLR Python runtime dependency needed by committed generated sources.
Do not add a nested package manager, backend registry, compatibility facade, or
dependency on the local KEDispatcher checkout.

Generated ANTLR files are committed so parsing does not require Java or a code
generator at runtime. Generated files are verified by regeneration and parser
runtime tests; lint/type-check exclusions, if required by generated code, must
target only the generated directory and be documented in `AGENTS.md`.

## Behavioral Compatibility

### Core IR

The Python model preserves the current nodes and fields:

- `Concept(name)`;
- `Constant(symbol, belong_concepts)`;
- `Operator(name, input_concepts, output_concept)` and `arity`;
- `CompoundTerm(operator, arguments)`;
- `ListTerm(items)`;
- `Assertion(lhs, rhs, relation_symbol)`;
- `ConnectiveFormula(formula_left, connective, formula_right)`;
- `IfTerm(condition, when_true, when_false)` once the parser layer lands;
- `Workflow(name, assertions)`;
- `WorkflowFile(constants, workflows)` once the parser layer lands.

Python uses frozen, slotted dataclasses where they express these data-only
contracts directly. `ConnectiveFormula` validates that `NOT` has no right
formula and `AND`/`OR` do have one. No global concept or operator registry is
introduced.

### Parser

The Python parser preserves the draft #4 runtime contract:

- lexer and parser errors return diagnostics and no Core IR;
- diagnostic lines and columns are 1-based;
- spans are half-open, and EOF errors have a visible width of one column;
- declaration and workflow source order is retained;
- duplicate declarations are retained, while term lookup uses the first;
- concepts, constants, and operators are reused within one parse only;
- quoted constant delimiters are stripped;
- boolean spellings normalize to lowercase `true` or `false`;
- top-level `==` lowers to relation symbol `=`;
- formula comparisons preserve `=`, `!=`, `<`, `<=`, `>`, and `>=`;
- arithmetic precedence and associativity come from the existing grammar;
- unary plus returns its operand, while unary minus becomes a one-argument
  compound term;
- lists and three-argument `if` expressions lower without approximation.

### Phase Results

Python functions use normal snake_case names:

- `parse_workflow`;
- `check_workflow`;
- `generate_typescript` or the compiler class introduced by the compiler PR;
- `check_planned_functions`.

Their result contracts remain equivalent to the current TypeScript contracts.
No camelCase aliases are added because no Python caller exists yet. Parser
errors are ordinary results. Unimplemented checker, planning, or concrete
generator behavior continues to fail explicitly rather than return approximate
output.

## Pull Request Sequence

### PR 1: Python foundation and phase contracts

Add the importable Python package, diagnostic/result contracts, parser/checker/
generator/planning boundaries, and the minimal dependency declaration. Keep the
existing TypeScript files temporarily so the stacked series has no broken
intermediate state.

### PR 2: Python Workflow Core IR

Add the minimal Python Core IR and contract tests. Preserve the deliberate
absence of KEDispatcher-only reasoning and execution nodes.

### PR 3: Python grammar toolchain

Keep `FusionFlow.g4` unchanged, port the grammar documentation contract test to
Python, generate Python-target ANTLR sources, and add a reproducibility check.

### PR 4: Python parser and Core IR visitor

Port draft #4's lexer/parser/listener/visitor behavior and parser runtime tests
to Python. This is the behavioral parity gate for syntax and lowering.

### PR 5: Python compiler scaffold and TypeScript removal

Port draft #5's Core IR traversal/compiler template to Python, port its
contract test, then remove the superseded TypeScript source, generated output,
Node package metadata, and TypeScript-only tests from `fusion-flow-next`.
Existing `fusion-flow` Node runtime files remain untouched.

## Testing

Each stacked PR must pass its focused tests plus repository checks appropriate
to the files it changes. The final stack must pass:

```powershell
uv run python -m pytest -q examples/haitun-workspace/skills/fusion-flow-next/test
uv run ruff check .
uv run ruff format --check .
uv run ty check
git diff --check origin/main...HEAD
```

Parser parity tests cover successful lowering, identity reuse, duplicate
declarations, boolean and quote normalization, arithmetic precedence,
conditional/list terms, malformed input, and EOF diagnostics. Generated-source
reproducibility is checked separately from runtime behavior.

## Documentation and Activation

Update the skill README as each boundary changes. Update root or workspace
documentation only when its stated commands or behavior change. Record any
intentional generated-code lint/type exclusion in `AGENTS.md`.

This migration does not add a prompt switch, workspace tool, runner hook, or
activation path. Those require a later design after concrete checker and
generator behavior exists.
