# FusionFlow Next Python Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the inactive FusionFlow Next TypeScript compiler path with a behavior-equivalent Python path in five stacked pull requests.

**Architecture:** Keep `grammar/FusionFlow.g4` as the syntax source of truth, commit ANTLR 4.13.2 Python output, and lower parse trees into a small frozen-dataclass Core IR. Preserve checker, generator, and planning phase boundaries as explicit Python APIs; do not activate the new path or modify the existing FusionFlow runtime.

**Tech Stack:** Python 3.14, `antlr4-python3-runtime` 4.13.x, dataclasses, pytest, Ruff, ty, uv.

---

## File map

- `fusion_flow_next/contracts.py`: diagnostic and parse/check/generate result values.
- `fusion_flow_next/core_ir.py`: the complete supported Workflow Core IR.
- `fusion_flow_next/parser.py`: ANTLR setup, syntax diagnostics, and handwritten lowering visitor.
- `fusion_flow_next/checker.py`: explicit unimplemented checker boundary.
- `fusion_flow_next/generator.py`: TypeScript compiler traversal scaffold.
- `fusion_flow_next/planning.py`: planning contracts and explicit unimplemented boundary.
- `fusion_flow_next/generated/`: committed ANTLR Python lexer/parser/visitor and grammar checksum.
- `test/`: Python contract tests; one focused file per shipped boundary.
- `grammar/FusionFlow.g4`: unchanged language source of truth.
- `README.md`: current Python module and regeneration instructions.
- `pyproject.toml`, `uv.lock`, `AGENTS.md`: runtime dependency and narrowly scoped generated-code exclusions.

The existing `fusion-flow-next/SKILL.md` and all files under the sibling `fusion-flow/` directory are out of scope.

## PR 1 — Python foundation and phase contracts

Branch: `codex/fusion-flow-python-foundation` from `main`.

### Task 1: Add the Python package and contracts

**Files:**
- Create: `examples/haitun-workspace/skills/fusion-flow-next/fusion_flow_next/__init__.py`
- Create: `examples/haitun-workspace/skills/fusion-flow-next/fusion_flow_next/contracts.py`
- Create: `examples/haitun-workspace/skills/fusion-flow-next/fusion_flow_next/parser.py`
- Create: `examples/haitun-workspace/skills/fusion-flow-next/fusion_flow_next/checker.py`
- Create: `examples/haitun-workspace/skills/fusion-flow-next/fusion_flow_next/generator.py`
- Create: `examples/haitun-workspace/skills/fusion-flow-next/fusion_flow_next/planning.py`
- Create: `examples/haitun-workspace/skills/fusion-flow-next/test/test_contracts.py`
- Modify: `examples/haitun-workspace/skills/fusion-flow-next/README.md`
- Modify: `pyproject.toml`
- Modify: `uv.lock`

- [ ] **Step 1: Write the failing boundary test**

```python
from __future__ import annotations

import pytest

from fusion_flow_next.checker import check_workflow
from fusion_flow_next.generator import generate_typescript
from fusion_flow_next.parser import parse_workflow
from fusion_flow_next.planning import check_planned_functions


def test_unimplemented_phase_boundaries_fail_explicitly() -> None:
    with pytest.raises(NotImplementedError):
        parse_workflow("")
    with pytest.raises(NotImplementedError):
        check_workflow(object())
    with pytest.raises(NotImplementedError):
        generate_typescript(object())
    with pytest.raises(NotImplementedError):
        check_planned_functions((), ())
```

- [ ] **Step 2: Run the test and confirm the package is absent**

Run:

```powershell
uv run --directory examples/haitun-workspace/skills/fusion-flow-next python -m pytest -q test/test_contracts.py
```

Expected: collection fails with `ModuleNotFoundError: No module named 'fusion_flow_next'`.

- [ ] **Step 3: Add frozen diagnostic/result contracts and explicit stubs**

Use frozen, slotted dataclasses for `SourcePosition`, `SourceSpan`, `Diagnostic`, `ParseResult`, `CheckResult`, `GenerateResult`, `PlannedSyntax`, `PlannedFunction`, and `PlanningCheckResult`. Use `Literal["error", "warning"]` for severity. In this first stack layer, type `core_ir` as `object`; PR 2 narrows it after `core_ir.py` exists. Each phase function raises exactly:

```python
raise NotImplementedError("FusionFlow Next <phase> is not implemented.")
```

Export the four phase functions and public contract dataclasses from `fusion_flow_next/__init__.py`. Add only this runtime dependency:

```toml
"antlr4-python3-runtime>=4.13.2,<4.14",
```

Run `uv lock` after editing `pyproject.toml`.

- [ ] **Step 4: Run focused and repository checks**

```powershell
uv run --directory examples/haitun-workspace/skills/fusion-flow-next python -m pytest -q test/test_contracts.py
uv run ruff check examples/haitun-workspace/skills/fusion-flow-next/fusion_flow_next examples/haitun-workspace/skills/fusion-flow-next/test/test_contracts.py
uv run ty check examples/haitun-workspace/skills/fusion-flow-next/fusion_flow_next
```

Expected: all commands pass.

- [ ] **Step 5: Commit and open draft PR 1**

```powershell
git add AGENTS.md pyproject.toml uv.lock examples/haitun-workspace/skills/fusion-flow-next docs/superpowers
git commit -m "feat(fusion-flow-next): add Python phase contracts"
git push -u origin codex/fusion-flow-python-foundation
```

Open a draft PR targeting `main`. Its description must say the TypeScript files remain temporarily and the new path is inactive.

## PR 2 — Python Workflow Core IR

Branch: `codex/fusion-flow-python-core-ir` from `codex/fusion-flow-python-foundation`.

### Task 2: Add the minimal Core IR

**Files:**
- Create: `examples/haitun-workspace/skills/fusion-flow-next/fusion_flow_next/core_ir.py`
- Create: `examples/haitun-workspace/skills/fusion-flow-next/test/test_core_ir.py`
- Modify: `examples/haitun-workspace/skills/fusion-flow-next/fusion_flow_next/contracts.py`
- Modify: `examples/haitun-workspace/skills/fusion-flow-next/fusion_flow_next/__init__.py`
- Modify: `examples/haitun-workspace/skills/fusion-flow-next/README.md`

- [ ] **Step 1: Write the Core IR contract test**

```python
from __future__ import annotations

import pytest

from fusion_flow_next.core_ir import (
    Assertion,
    CompoundTerm,
    Concept,
    ConnectiveFormula,
    Constant,
    IfTerm,
    ListTerm,
    Operator,
    Workflow,
    WorkflowFile,
)


def test_workflow_core_ir_contract() -> None:
    step = Concept("Step")
    item = Constant("item", (step,))
    operator = Operator("identity", (step,), step)
    assertion = Assertion(CompoundTerm(operator, (item,)), ListTerm((item,)))
    condition = ConnectiveFormula(assertion, "NOT")
    conditional = IfTerm(condition, item, item)
    workflow = Workflow("example", (Assertion(conditional, item),))
    workflow_file = WorkflowFile((item,), (workflow,))

    assert operator.arity == 1
    assert workflow_file.workflows[0].assertions[0].lhs is conditional
    with pytest.raises(ValueError, match="NOT cannot have a right formula"):
        ConnectiveFormula(assertion, "NOT", assertion)
    with pytest.raises(ValueError, match="AND requires a right formula"):
        ConnectiveFormula(assertion, "AND")
```

- [ ] **Step 2: Run the test and confirm `core_ir` is absent**

```powershell
uv run --directory examples/haitun-workspace/skills/fusion-flow-next python -m pytest -q test/test_core_ir.py
```

Expected: collection fails because `fusion_flow_next.core_ir` does not exist.

- [ ] **Step 3: Implement the exact Core IR nodes**

Create frozen, slotted dataclasses with snake-case fields:

```python
@dataclass(frozen=True, slots=True)
class Concept:
    name: str


@dataclass(frozen=True, slots=True)
class Constant:
    symbol: str
    belong_concepts: tuple[Concept, ...] = ()


@dataclass(frozen=True, slots=True)
class Operator:
    name: str
    input_concepts: tuple[Concept, ...] = ()
    output_concept: Concept | None = None

    @property
    def arity(self) -> int:
        return len(self.input_concepts)


@dataclass(frozen=True, slots=True)
class CompoundTerm:
    operator: Operator
    arguments: tuple[Term, ...]


@dataclass(frozen=True, slots=True)
class ListTerm:
    items: tuple[Term, ...]


@dataclass(frozen=True, slots=True)
class Assertion:
    lhs: Term
    rhs: Term
    relation_symbol: RelationSymbol = "="


@dataclass(frozen=True, slots=True)
class ConnectiveFormula:
    formula_left: Formula
    connective: LogicalConnective
    formula_right: Formula | None = None

    def __post_init__(self) -> None:
        if self.connective == "NOT" and self.formula_right is not None:
            raise ValueError("NOT cannot have a right formula")
        if self.connective != "NOT" and self.formula_right is None:
            raise ValueError(f"{self.connective} requires a right formula")


@dataclass(frozen=True, slots=True)
class IfTerm:
    condition: Formula
    when_true: Term
    when_false: Term


@dataclass(frozen=True, slots=True)
class Workflow:
    name: str
    assertions: tuple[Assertion, ...]


@dataclass(frozen=True, slots=True)
class WorkflowFile:
    constants: tuple[Constant, ...]
    workflows: tuple[Workflow, ...]


type RelationSymbol = Literal["=", "!=", "<", "<=", ">", ">="]
type LogicalConnective = Literal["NOT", "AND", "OR"]
type Term = Constant | CompoundTerm | ListTerm | IfTerm
type Formula = Assertion | ConnectiveFormula
```

Place the aliases after the classes; postponed annotations make recursive fields valid. Narrow `ParseResult.core_ir` to `WorkflowFile | None` and `CheckResult.core_ir` to `Workflow`. Re-export all nodes and aliases.

- [ ] **Step 4: Run focused checks**

```powershell
uv run --directory examples/haitun-workspace/skills/fusion-flow-next python -m pytest -q test/test_contracts.py test/test_core_ir.py
uv run ruff check examples/haitun-workspace/skills/fusion-flow-next/fusion_flow_next examples/haitun-workspace/skills/fusion-flow-next/test
uv run ty check examples/haitun-workspace/skills/fusion-flow-next/fusion_flow_next
```

Expected: all commands pass.

- [ ] **Step 5: Commit and open draft PR 2**

```powershell
git switch -c codex/fusion-flow-python-core-ir
git add examples/haitun-workspace/skills/fusion-flow-next
git commit -m "feat(fusion-flow-next): add Python Workflow Core IR"
git push -u origin codex/fusion-flow-python-core-ir
```

Open a draft PR targeting `codex/fusion-flow-python-foundation`.

## PR 3 — Python grammar toolchain

Branch: `codex/fusion-flow-python-grammar` from `codex/fusion-flow-python-core-ir`.

### Task 3: Commit generated Python ANTLR sources

**Files:**
- Create: `examples/haitun-workspace/skills/fusion-flow-next/fusion_flow_next/generated/__init__.py`
- Create: `examples/haitun-workspace/skills/fusion-flow-next/fusion_flow_next/generated/FusionFlowLexer.py`
- Create: `examples/haitun-workspace/skills/fusion-flow-next/fusion_flow_next/generated/FusionFlowParser.py`
- Create: `examples/haitun-workspace/skills/fusion-flow-next/fusion_flow_next/generated/FusionFlowVisitor.py`
- Create: `examples/haitun-workspace/skills/fusion-flow-next/fusion_flow_next/generated/FusionFlowLexer.interp`
- Create: `examples/haitun-workspace/skills/fusion-flow-next/fusion_flow_next/generated/FusionFlowLexer.tokens`
- Create: `examples/haitun-workspace/skills/fusion-flow-next/fusion_flow_next/generated/FusionFlow.interp`
- Create: `examples/haitun-workspace/skills/fusion-flow-next/fusion_flow_next/generated/FusionFlow.tokens`
- Create: `examples/haitun-workspace/skills/fusion-flow-next/fusion_flow_next/generated/FusionFlow.sha256`
- Create: `examples/haitun-workspace/skills/fusion-flow-next/test/test_grammar.py`
- Modify: `examples/haitun-workspace/skills/fusion-flow-next/README.md`
- Modify: `AGENTS.md`
- Modify: `pyproject.toml`

- [ ] **Step 1: Port the grammar documentation test and stale-generation gate**

Use `pathlib.Path` only in this synchronous test. Parse preset names and signature comments with the two existing regular expressions. Assert that the sorted names match, each parameter is an upper-camel identifier, and parameter count equals documented arity. Add:

```python
def test_generated_parser_matches_grammar_checksum() -> None:
    grammar = ROOT / "grammar" / "FusionFlow.g4"
    expected = hashlib.sha256(grammar.read_bytes()).hexdigest()
    actual = (ROOT / "fusion_flow_next" / "generated" / "FusionFlow.sha256").read_text().strip()
    assert actual == expected
```

- [ ] **Step 2: Run the test and confirm generated files are missing**

```powershell
uv run --directory examples/haitun-workspace/skills/fusion-flow-next python -m pytest -q test/test_grammar.py
```

Expected: checksum test fails because `FusionFlow.sha256` is absent.

- [ ] **Step 3: Generate with ANTLR 4.13.2 and record the grammar hash**

From `examples/haitun-workspace/skills/fusion-flow-next`, run the pinned ANTLR 4.13.2 tool:

```powershell
antlr4 -v 4.13.2 -Dlanguage=Python3 -visitor -no-listener -Xexact-output-dir -o fusion_flow_next/generated grammar/FusionFlow.g4
```

Then write the lowercase SHA-256 of `grammar/FusionFlow.g4` followed by one newline to `fusion_flow_next/generated/FusionFlow.sha256`, and add an empty `generated/__init__.py`.

The checksum is the deliberate lightweight regeneration gate: it detects a changed grammar without requiring Java in normal test runs. Regenerate with the pinned command whenever it fails.

- [ ] **Step 4: Exclude only generated Python from handwritten lint/type checks**

Add the generated directory to Ruff's `extend-exclude` and ty's source `exclude`; do not add inline suppressions. Record this exception and the checksum rule in root `AGENTS.md`. Keep `grammar/FusionFlow.g4` byte-for-byte unchanged.

- [ ] **Step 5: Run grammar and import checks**

```powershell
uv run --directory examples/haitun-workspace/skills/fusion-flow-next python -m pytest -q test/test_grammar.py
uv run --directory examples/haitun-workspace/skills/fusion-flow-next python -c "from fusion_flow_next.generated.FusionFlowLexer import FusionFlowLexer; from fusion_flow_next.generated.FusionFlowParser import FusionFlowParser"
uv run ruff check .
uv run ty check
```

Expected: all commands pass.

- [ ] **Step 6: Commit and open draft PR 3**

```powershell
git switch -c codex/fusion-flow-python-grammar
git add AGENTS.md pyproject.toml examples/haitun-workspace/skills/fusion-flow-next
git commit -m "feat(fusion-flow-next): generate Python parser"
git push -u origin codex/fusion-flow-python-grammar
```

Open a draft PR targeting `codex/fusion-flow-python-core-ir`.

## PR 4 — Python parser and Core IR visitor

Branch: `codex/fusion-flow-python-parser` from `codex/fusion-flow-python-grammar`.

### Task 4: Lower the current grammar without semantic checking

**Files:**
- Modify: `examples/haitun-workspace/skills/fusion-flow-next/fusion_flow_next/parser.py`
- Create: `examples/haitun-workspace/skills/fusion-flow-next/test/test_parser.py`
- Modify: `examples/haitun-workspace/skills/fusion-flow-next/README.md`

- [ ] **Step 1: Port the PR4 parser contract to pytest**

Use one successful source containing declarations, two workflows, calls, booleans, quotes, `if`, `NOT`/`AND`, comparisons, arithmetic, lists, unary minus, and right-associative power. Assert:

```python
assert result.diagnostics == ()
assert [item.symbol for item in file.constants] == ["review", "draft", "backup"]
assert [workflow.name for workflow in file.workflows] == ["first", "second"]
assert review.belong_concepts[1] is backup.belong_concepts[0]
assert first_custom.operator is second_custom.operator is arithmetic_call.operator
assert first_custom.arguments[1] is review
assert first_assertion.rhs.symbol == "true"
assert second_assertion.rhs.symbol == "false"
assert arithmetic_assertion.rhs is first_assertion.rhs
assert conditional.condition.connective == "AND"
assert conditional.condition.formula_left.connective == "NOT"
assert not_equals.relation_symbol == "!="
assert numeric_equals.relation_symbol == "="
assert sum_term.operator.name == "+"
assert sum_term.arguments[1].operator.name == "*"
assert negation.operator.name == "-"
assert power.arguments[1].operator.name == "^"
```

Add duplicate-declaration assertions using `is not` for the duplicate objects and `is` for term lookup of the first declaration. Add malformed `=` and missing-`}` cases proving `core_ir is None`, 1-based columns, half-open spans, and EOF width one.

- [ ] **Step 2: Run the parser test and confirm the stub fails**

```powershell
uv run --directory examples/haitun-workspace/skills/fusion-flow-next python -m pytest -q test/test_parser.py
```

Expected: fails with `NotImplementedError: FusionFlow Next parser is not implemented.`

- [ ] **Step 3: Implement ANTLR setup and diagnostic collection**

Use `InputStream`, `CommonTokenStream`, and the generated lexer/parser. Remove default error listeners from both. Install one listener whose callback appends:

```python
Diagnostic(
    severity="error",
    message=message,
    span=SourceSpan(
        start=SourcePosition(line=line, column=column + 1),
        end=SourcePosition(line=line, column=column + 1 + width),
    ),
)
```

Set `width` to one for EOF and otherwise to `max(len(token.text or ""), 1)`. Bind ANTLR's required `syntaxError` callback name to a snake-case instance method with `setattr`; do not add a Ruff suppression.

- [ ] **Step 4: Implement the handwritten `_CoreIrVisitor`**

The visitor owns only three parse-local dictionaries:

```python
self._concepts: dict[str, Concept] = {}
self._constants: dict[str, Constant] = {}
self._operators: dict[str, Operator] = {}
```

Implement direct snake-case methods for workflow file, declarations, workflows, assertions, formula, comparison, term, if-expression, list, and atomic term contexts. Do not subclass the generated visitor; direct context dispatch avoids Java-style method names in handwritten code.

Required lowering rules:

```python
# declarations retain duplicates; lookup keeps the first
constant = Constant(symbol, concepts)
self._constants.setdefault(symbol, constant)

# top-level assertion equality
Assertion(lhs, rhs, "=")

# unary plus / minus
return operand if context.op.text == "+" else CompoundTerm(self._operator("-"), (operand,))

# binary arithmetic
return CompoundTerm(self._operator(context.op.text), (left, right))

# literals
if symbol.startswith('"') and symbol.endswith('"'):
    symbol = symbol[1:-1]
if symbol.lower() in {"true", "false"}:
    symbol = symbol.lower()
```

Reuse concepts, constants, and operators only within that visitor instance. Return `ParseResult(core_ir=None, diagnostics=...)` on any lexer/parser diagnostic; otherwise visit the complete `workflowFile` tree.

- [ ] **Step 5: Run parser parity and static checks**

```powershell
uv run --directory examples/haitun-workspace/skills/fusion-flow-next python -m pytest -q test/test_parser.py
uv run --directory examples/haitun-workspace/skills/fusion-flow-next python -m pytest -q test
uv run ruff check .
uv run ruff format --check .
uv run ty check
```

Expected: all commands pass.

- [ ] **Step 6: Commit and open draft PR 4**

```powershell
git switch -c codex/fusion-flow-python-parser
git add examples/haitun-workspace/skills/fusion-flow-next
git commit -m "feat(fusion-flow-next): parse DSL with Python"
git push -u origin codex/fusion-flow-python-parser
```

Open a draft PR targeting `codex/fusion-flow-python-grammar`. Compare its parser test coverage against draft PR #4 before declaring parity.

## PR 5 — Python compiler scaffold and TypeScript removal

Branch: `codex/fusion-flow-python-compiler` from `codex/fusion-flow-python-parser`.

### Task 5: Port the compiler traversal and remove superseded Node files

**Files:**
- Modify: `examples/haitun-workspace/skills/fusion-flow-next/fusion_flow_next/generator.py`
- Create: `examples/haitun-workspace/skills/fusion-flow-next/test/test_generator.py`
- Modify: `examples/haitun-workspace/skills/fusion-flow-next/README.md`
- Delete: `examples/haitun-workspace/skills/fusion-flow-next/src/`
- Delete: `examples/haitun-workspace/skills/fusion-flow-next/generated/`
- Delete: `examples/haitun-workspace/skills/fusion-flow-next/test/core-ir-contract.ts`
- Delete: `examples/haitun-workspace/skills/fusion-flow-next/test/grammar-contract.mjs`
- Delete: `examples/haitun-workspace/skills/fusion-flow-next/package.json`
- Delete: `examples/haitun-workspace/skills/fusion-flow-next/package-lock.json`
- Delete: `examples/haitun-workspace/skills/fusion-flow-next/tsconfig.json`
- Modify or delete: `examples/haitun-workspace/skills/fusion-flow-next/.gitignore`

- [ ] **Step 1: Write the compiler traversal contract**

Create a concrete recording subclass in the test. It must render constants, calls, lists, assertions, and connectives through the protected traversal methods. Verify:

```python
assert compiler.compile(blocked) == GenerateResult(code=None, diagnostics=())
assert compiler.compile(allowed).code == "example:identity(value) = [value]"
assert compiler.compile_term_for_contract(value) == "value"
assert compiler.compile_formula_for_contract(assertion) == "identity(value) = [value]"
with pytest.raises(TypeError, match="unsupported term node of type IfTerm"):
    compiler.compile_term_for_contract(IfTerm(assertion, value, value))
```

- [ ] **Step 2: Run the test and confirm the compiler class is absent**

```powershell
uv run --directory examples/haitun-workspace/skills/fusion-flow-next python -m pytest -q test/test_generator.py
```

Expected: collection fails because `TypeScriptCompiler` is not exported.

- [ ] **Step 3: Implement the minimal abstract compiler traversal**

Create `TypeScriptCompiler(ABC)` with final public `compile`, protected `compile_formula` and `compile_term`, abstract hooks for `compile_constant`, `compile_compound_term`, `compile_list_term`, `compile_assertion`, `compile_connective_formula`, and `build_program`. Dispatch with `isinstance` in the same order as draft PR #5. Unsupported nodes raise:

```python
raise TypeError(
    f"{type(self).__name__} cannot compile unsupported {label} node "
    f"of type {type(node).__name__}."
)
```

When `check_result.can_generate` is false, return `GenerateResult(code=None, diagnostics=())` without traversing. Do not add a concrete emitter, backend registry, or `IfTerm` approximation.

- [ ] **Step 4: Remove only superseded TypeScript compiler files**

Delete the listed Node metadata, TypeScript sources/tests, and top-level TypeScript `generated/` directory. Keep all Python files, `grammar/FusionFlow.g4`, `README.md`, and `SKILL.md`. Update README commands and module names to Python.

- [ ] **Step 5: Run final stack verification**

```powershell
uv run --directory examples/haitun-workspace/skills/fusion-flow-next python -m pytest -q test
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest -q
git diff --check origin/main...HEAD
```

Expected: all commands pass. Confirm `git diff --name-only origin/main...HEAD` contains no change beneath `examples/haitun-workspace/skills/fusion-flow/` and no change to `fusion-flow-next/SKILL.md`.

- [ ] **Step 6: Commit and open draft PR 5**

```powershell
git switch -c codex/fusion-flow-python-compiler
git add AGENTS.md pyproject.toml uv.lock examples/haitun-workspace/skills/fusion-flow-next
git commit -m "feat(fusion-flow-next): replace compiler scaffold with Python"
git push -u origin codex/fusion-flow-python-compiler
```

Open a draft PR targeting `codex/fusion-flow-python-parser`.

## Final PR-chain checks

- [ ] Every PR targets the immediately preceding branch, with PR 1 targeting `main`.
- [ ] Each PR description is based on all commits since its base branch.
- [ ] Draft PR #4 and draft PR #5 remain open until Python PR 4 and PR 5 pass.
- [ ] Close the superseded TypeScript drafts only after the replacement checks are green.
- [ ] Leave FusionFlow Next inactive; activation needs a separate design after real checker and concrete generator behavior exist.
