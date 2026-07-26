# FusionFlow Instruction Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add workflow-relative instruction path syntax, preserve executor-owned resolution, migrate the supplied catalyst workflow to current G4, and test every reachable backend stage.

**Architecture:** A dedicated `RELATIVE_PATH_ID` token lowers to the existing Core IR `Constant`, while assertion output-concept inference types it as `Instruction`. `WorkflowGraph` continues to store only `instruction_id`; the example dispatcher uses Core IR executor concepts to pass paths unchanged to Agent/Program executors and resolve UTF-8 contents only for Human executors.

**Tech Stack:** ANTLR 4.13.2, Python 3.14, AnyIO, pytest, Ruff, ty, DeepSeek through `any_llm`.

---

### Task 1: Parse Relative Instruction Paths

**Files:**
- Modify: `examples/haitun-workspace/skills/fusion-flow-next/grammar/FusionFlow.g4`
- Modify: `examples/haitun-workspace/skills/fusion-flow-next/fusion_flow_next/parser.py`
- Modify: `examples/haitun-workspace/skills/fusion-flow-next/generated/FusionFlowLexer.py`
- Modify: `examples/haitun-workspace/skills/fusion-flow-next/generated/FusionFlowParser.py`
- Test: `examples/haitun-workspace/skills/fusion-flow-next/test/test_parser.py`
- Test: `examples/haitun-workspace/skills/fusion-flow-next/test/test_grammar.py`

- [ ] **Step 1: Write the failing parser test**

Add `Instruction` to `_context()` and register a typed operator:

```python
operators["step_instruction"] = Operator(
    name="step_instruction",
    input_concepts=(concepts["Step"],),
    output_concept=concepts["Instruction"],
)
```

Then parse:

```python
result = parse_workflow(
    """
    const review: Step;
    workflow path_instruction {
      step_instruction(review) == "./instructions/review-file.md";
    }
    """,
    context=_context(),
)
assert isinstance(result.core_ir, WorkflowFile)
instruction = result.core_ir.workflows[0].assertions[0].rhs
assert isinstance(instruction, Constant)
assert instruction.symbol == "./instructions/review-file.md"
assert [concept.name for concept in instruction.belong_concepts] == ["Instruction"]
```

- [ ] **Step 2: Run the focused test and verify RED**

Run from `examples/haitun-workspace/skills/fusion-flow-next`:

```powershell
uv run python -m pytest -q test/test_parser.py -k instruction_path --no-cov -p no:cacheprovider
```

Expected: parser diagnostics for `/` or `-`, or concept inference failure.

- [ ] **Step 3: Add the minimal grammar and inference**

Extend `constantName` without broadening existing quoted identities:

```antlr
constantName
    : NUMBER
    | RELATIVE_PATH_ID
    | QUOTEDCONSTANTID
    | LOWID
    ;

RELATIVE_PATH_ID : '"./' [A-Za-z0-9._/-]+ '"';
```

In `visit_assertion`, infer each side from the opposite top-level call:

```python
terms = context.term()
return Assertion(
    lhs=self.visit_term(terms[0], self._term_output_concept(terms[1])),
    rhs=self.visit_term(terms[1], self._term_output_concept(terms[0])),
)
```

Add one private helper that returns `operator.output_concept` only for a
top-level operator call; otherwise it returns `None`.

- [ ] **Step 4: Regenerate the committed ANTLR runtime**

Use the repository-pinned ANTLR 4.13.2 JAR and SHA-256 from `.github/workflows/ci.yml`:

```powershell
java -jar antlr-4.13.2-complete.jar -Dlanguage=Python3 -no-listener -Xexact-output-dir -o fusion_flow_next/generated grammar/FusionFlow.g4
```

Delete generated `.interp`, `.tokens`, and visitor files if emitted; only the
runtime lexer/parser files listed by `test/test_grammar.py` remain.

- [ ] **Step 5: Run parser and grammar tests**

```powershell
uv run python -m pytest -q test/test_parser.py test/test_grammar.py --no-cov -p no:cacheprovider
```

Expected: all pass.

- [ ] **Step 6: Commit**

```text
feat(fusion-flow-next): parse instruction paths

Lore: Infer path constants from step_instruction output types while preserving existing identity syntax.
Constraint: Relative path syntax begins with ./ and Core IR gains no new term type.
Tested: focused parser and grammar pytest
Co-authored-by: OmX <omx@oh-my-codex.dev>
```

### Task 2: Dispatch Paths by Executor Kind

**Files:**
- Modify: `examples/haitun-workspace/skills/fusion-flow-next/examples/run_workflow.py`
- Modify: `examples/haitun-workspace/skills/fusion-flow-next/test/test_examples.py`
- Create: `examples/haitun-workspace/skills/fusion-flow-next/test/fixtures/instructions/human.md`

- [ ] **Step 1: Write failing Agent, Program, and Human tests**

Build workflows whose executor constants belong to `Agent`, `Program`, and
`Human`. Capture completion prompts and assert:

```python
assert "Instruction: ./instructions/missing-agent.md" in agent_prompt
assert "Instruction: ./instructions/missing-program.md" in program_prompt
assert "人工审核中文说明" in human_prompt
assert "./instructions/human.md" not in human_prompt
```

Also assert Human failures for missing, empty, absolute, `..`, directory, and
symlink-escaping paths. Skip only the symlink case when Windows denies symlink
creation.

- [ ] **Step 2: Run the focused tests and verify RED**

```powershell
uv run python -m pytest -q test/test_examples.py -k instruction --no-cov -p no:cacheprovider
```

Expected: current dispatcher always forwards `instruction_id` and has no
executor-kind or workflow-path inputs.

- [ ] **Step 3: Preserve executor concepts beside the graph**

Introduce one example-local compiled value:

```python
@dataclass(frozen=True, slots=True)
class CompiledWorkflow:
    graph: WorkflowGraph
    executor_kinds: Mapping[str, str]
```

Build `executor_kinds` from parsed Core IR constants tagged with exactly one of
`Human`, `Agent`, or `Program`. Do not add `executor_kind` to `StepNode`.

- [ ] **Step 4: Implement Human-only path resolution**

Pass `workflow_path` and `executor_kinds` into the dispatcher closure.

```python
if instruction_id.startswith("./") and executor_kind == "Human":
    instruction = await _read_human_instruction(workflow_path, instruction_id)
else:
    instruction = instruction_id
```

The AnyIO resolver:

- requires a `.workflow` path for Human path instructions;
- rejects absolute and `..` paths before I/O;
- resolves the workflow parent and target;
- rejects symlink escape with normalized `os.path.commonpath`;
- requires a regular non-empty UTF-8 file.

Agent and Program branches perform no existence check and forward the original
relative reference.

- [ ] **Step 5: Run example tests**

```powershell
uv run python -m pytest -q test/test_examples.py --no-cov -p no:cacheprovider
```

Expected: all pass.

- [ ] **Step 6: Commit**

```text
feat(fusion-flow-next): dispatch instruction references

Lore: Pass path references to Agent and Program executors while resolving Human instructions beside the workflow.
Constraint: Executor classification stays outside WorkflowGraph.
Tested: focused example dispatcher pytest
Co-authored-by: OmX <omx@oh-my-codex.dev>
```

### Task 3: Migrate the Catalyst Workflow

**Files:**
- Create: `examples/haitun-workspace/skills/fusion-flow-next/examples/catalyst/catalyst.workflow`
- Create: `examples/haitun-workspace/skills/fusion-flow-next/examples/catalyst/instructions/prepare-workflow.md`
- Create: `examples/haitun-workspace/skills/fusion-flow-next/examples/catalyst/instructions/recommend-candidate.md`
- Create: `examples/haitun-workspace/skills/fusion-flow-next/examples/catalyst/instructions/prove-performance.md`
- Create: `examples/haitun-workspace/skills/fusion-flow-next/examples/catalyst/instructions/sample-structure.md`
- Create: `examples/haitun-workspace/skills/fusion-flow-next/examples/catalyst/instructions/evaluate-structures.md`
- Create: `examples/haitun-workspace/skills/fusion-flow-next/examples/catalyst/instructions/design-synthesis-route.md`
- Create: `examples/haitun-workspace/skills/fusion-flow-next/examples/catalyst/instructions/analyze-route-feasibility.md`
- Create: `examples/haitun-workspace/skills/fusion-flow-next/examples/catalyst/instructions/shutdown-workflow.md`
- Create: `examples/haitun-workspace/skills/fusion-flow-next/test/test_catalyst_example.py`

- [ ] **Step 1: Write the failing migration test**

Read `catalyst.workflow` and all Markdown files explicitly as UTF-8. Assert:

```python
assert parsed.diagnostics == ()
assert len(path_instruction_steps) == 11
assert len(set(path_instruction_steps.values())) == 8
assert all(path.startswith("./instructions/") for path in path_instruction_steps.values())
```

Assert the four recommendation Steps share
`./instructions/recommend-candidate.md`, and every referenced instruction file
exists and is non-empty.

- [ ] **Step 2: Add the source fixture without semantic edits**

Starting from `D:/Downloads/workflow2.0.zip`:

- change the 152 assertion separators from `=` to `==`;
- change the seven legacy multi-value braces to square brackets;
- declare the ten referenced `StepName` identities;
- add the missing feasibility Step name declaration and relation;
- update comments that still describe the old equality/list syntax.

Do not change producer, consumer, resource, retry, external catalog, or workflow
boundary assertions.

- [ ] **Step 3: Extract the eight instruction bodies**

Move the exact text between each `开始instruction`/`结束instruction` comment pair
to the named Markdown file. Replace all eleven relations with path constants;
the four recommendation Steps keep one shared path.

- [ ] **Step 4: Run parse and reference tests**

```powershell
uv run python -m pytest -q test/test_catalyst_example.py --no-cov -p no:cacheprovider
```

Expected: parse and instruction-reference assertions pass.

- [ ] **Step 5: Probe later backend stages**

The test calls `WorkflowGraphCompiler` after successful parsing. Preserve and
assert the first real unsupported semantic error rather than deleting source
relations. If compilation advances after another implementation change, update
the assertion to the next real boundary and call `generate_plan`.

- [ ] **Step 6: Commit**

```text
examples(fusion-flow-next): migrate catalyst workflow

Lore: Preserve the catalyst workflow topology while moving eight instruction bodies into path-backed files.
Constraint: Syntax migration does not remove unsupported producers, resources, or external assertions.
Tested: catalyst parse and staged backend pytest
Co-authored-by: OmX <omx@oh-my-codex.dev>
```

### Task 4: Synchronize Examples and Documentation

**Files:**
- Modify: `examples/haitun-workspace/skills/fusion-flow-next/examples/single_step.workflow`
- Modify: `examples/haitun-workspace/skills/fusion-flow-next/examples/sequential.workflow`
- Modify: `examples/haitun-workspace/skills/fusion-flow-next/examples/parallel_join.workflow`
- Modify: `examples/haitun-workspace/skills/fusion-flow-next/README.md`
- Modify: `docs/architecture/workflow/2026-07-23-workflow-graph-design.zh.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Add one short path-backed example**

Use an Agent executor and one `./instructions/...` relation to demonstrate that
the runner forwards the reference rather than preloading it. Keep the other
short examples identity-backed for compatibility coverage.

- [ ] **Step 2: Document the contract**

Document:

- exact `./` syntax;
- output-concept inference;
- Agent/Program pass-through;
- Human-only UTF-8 resolution and path containment;
- graph schema compatibility;
- catalyst sample's current staged backend boundary;
- checker remains unimplemented.

Add the executor-owned resolution decision to `AGENTS.md` because it is
intentional and otherwise easy to “fix” incorrectly later. Do not edit
`SKILL.md`.

- [ ] **Step 3: Run documentation and example checks**

```powershell
uv run python -m pytest -q test --no-cov -p no:cacheprovider
uv run ruff check .
uv run ruff format --check .
uv run ty check
git diff --check
```

Expected: all pass.

- [ ] **Step 4: Commit**

```text
docs(workflow): explain instruction references

Lore: Record executor-owned path handling and the catalyst workflow's supported execution boundary.
Constraint: Documentation does not claim checker, resource, or multi-producer support.
Tested: FusionFlow Next pytest, Ruff, ty, and diff check
Co-authored-by: OmX <omx@oh-my-codex.dev>
```

### Task 5: End-to-End Verification and PR

**Files:**
- Review all files changed from `origin/main`

- [ ] **Step 1: Run the full focused matrix**

```powershell
uv run python -m pytest -q examples/haitun-workspace/skills/fusion-flow-next/test --no-cov -p no:cacheprovider
uv run python -m pytest -q tests/psi_agent/test_workflow_execution.py tests/psi_agent/workflow_graph --no-cov -p no:cacheprovider
uv run ruff check .
uv run ruff format --check .
uv run ty check
git diff --check origin/main...HEAD
```

- [ ] **Step 2: Re-run live DeepSeek examples**

Load `D:/Downloads/deepseek_api.txt` into the child process environment without
printing or storing it. Run the three short workflows. Confirm Agent path
instructions are passed unchanged; do not claim DeepSeek read local files.

- [ ] **Step 3: Run the catalyst staged probe**

Record:

- parse result;
- instruction path/reference counts;
- graph compilation result or first exact error;
- plan generation result or first exact error;
- whether any executor calls were reachable.

- [ ] **Step 4: Request two-stage review**

Run one requirements review and one code-quality/security review. Address only
actionable findings inside this PR's scope, then repeat focused verification.

- [ ] **Step 5: Publish**

Push `codex/fusion-flow-next-examples` and create a PR against `msg-bq/psi-agent`
`main`. The PR description lists:

- A-style syntax and compatibility;
- executor-kind dispatch behavior;
- catalyst syntax migration and preserved semantic blockers;
- exact test commands and live API evidence;
- explicit non-goals and remaining execution boundaries.
