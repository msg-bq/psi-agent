# FusionFlow Instruction Path Design

## Context

`step_instruction(Step) -> Instruction` currently preserves only an
`instruction_id` in `WorkflowGraph`. Long instruction bodies in real workflows
therefore remain comments and never reach the dispatcher. The workflow
execution layer intentionally receives an injected dispatcher and does not own
catalog or filesystem resolution.

## Goals

- Allow a Step to reference a UTF-8 instruction file directly:

  ```fusionflow
  step_instruction(step) == "./instructions/recommend.md";
  ```

- Keep existing symbolic instruction identities compatible.
- Let each executor kind consume an instruction reference appropriately.
- Migrate the supplied catalyst workflow to current G4 syntax without changing
  its dataflow semantics.
- Test each supported stage honestly: parse, graph compilation, plan generation,
  and execution.

## Non-goals

- Embedding free-form instruction text in G4 source.
- Adding instruction contents or machine-specific paths to `WorkflowGraph`.
- Implementing multi-producer artifacts, resource scheduling, retries, loops, or
  the unfinished static checker.
- Removing unsupported assertions merely to make the catalyst workflow execute.

## Surface Syntax

The grammar gains a quoted relative-path constant beginning with `./`. It uses
portable `/` separators and allows ordinary filename characters, including
`.` and `-`. Existing restricted quoted identities and lowercase identities
retain their current behavior.

The parser uses a call operator's declared output concept to infer the concept
of the opposite assertion term. With the catalog signature
`step_instruction(Step) -> Instruction`, the path is therefore inferred as an
`Instruction` without a duplicate `const` declaration.

The Core IR and graph compiler remain unchanged in shape: the path text is a
`Constant.symbol` and becomes `StepNode.instruction_id`.

## Dispatch Semantics

The dispatcher already owns executor lookup. It uses the executor concept from
the external catalog or parsed Core IR; `WorkflowGraph` does not gain a
duplicate `executor_kind` field.

- Agent Steps receive the original `./instructions/example.md` reference. The
  runner does not read the file or replace the reference with its contents; a
  file-capable agent resolves it.
- Human Steps resolve the path against the `.workflow` file's parent directory
  and receive the UTF-8 instruction contents.
- Program Steps retain the path reference. Program-specific argument or file
  handling remains the program executor's responsibility.
- Values not beginning with `./` remain symbolic instruction identities for all
  executor kinds.

Human path resolution rejects absolute paths, `..` traversal, missing files,
directories, empty files, and symlink escapes. The graph and execution plan
continue to carry only stable metadata.

## Catalyst Workflow Migration

The supplied `workflow2.0.zip` contains one catalyst workflow and eight distinct
instruction bodies shared by eleven Steps. The migrated fixture will:

1. convert assertion `=` tokens to current G4 `==`;
2. convert seven legacy multi-value `{...}` terms to `[...]`;
3. declare the ten existing StepName values and add the missing
   `synthesis_route_feasibility_analysis_step` name relation;
4. move the eight instruction comment bodies into eight Markdown files;
5. replace the eleven `step_instruction` values with relative paths, preserving
   the four recommendation Steps' shared instruction;
6. update only comments that describe obsolete syntax.

No producer, consumer, resource, retry, or catalog assertion is removed or
rewritten for backend convenience.

## Errors

Grammar errors remain ordinary parser diagnostics. Unknown concepts and
incompatible typed-identity uses remain parser `ValueError`s. Human
path-resolution errors identify the Step and invalid instruction path without
exposing file contents or credentials. Agent and Program dispatch do not
require the referenced file to exist locally because their executor owns
resolution.

The migrated catalyst workflow is expected to pass parsing. If graph compilation
or plan generation rejects its existing semantics, the test and run report keep
the first exact backend error instead of masking it.

## Tests

- Parser accepts `./instructions/example-name.md` as an inferred Instruction and
  preserves its symbol.
- Existing instruction identities parse and compile unchanged.
- Agent dispatch receives the unchanged relative instruction path and performs
  no local file read.
- Human dispatch loads UTF-8 instruction contents.
- Human dispatch rejects missing, empty, absolute, traversing, directory, and
  symlink-escaping paths clearly.
- Program dispatch receives the unchanged instruction path.
- The three short workflows still parse, compile, plan, and execute with a mock
  completion function.
- The migrated catalyst workflow has zero parser diagnostics and all eleven
  Steps reference the expected eight instruction files.
- Testing continues through graph compilation and plan generation, recording
  the first unsupported semantic boundary.

## PR Scope

The PR includes the existing short examples and runner, G4/parser support for
relative instruction paths, the migrated catalyst fixture and instruction
files, focused tests, generated ANTLR runtime updates, and synchronized workflow
documentation. It does not modify the repository `SKILL.md`.
