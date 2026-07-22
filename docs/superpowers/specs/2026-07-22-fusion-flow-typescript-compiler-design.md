# FusionFlow TypeScript Compiler Scaffold Design

## Goal

Add the smallest useful Core IR-to-TypeScript compiler framework for FusionFlow Next without implementing TypeScript emission or touching the BNF/parser workstream.

## Design

Keep the framework in the existing `src/generator.ts` module. Replace the throwing function placeholder with an abstract `TypeScriptCompiler` template class that:

- accepts a checker-owned `CheckResult`;
- refuses generation when `canGenerate` is false;
- dispatches the current `Term` and `Formula` unions to node-specific hooks;
- compiles a `Workflow` by compiling its ordered assertions and passing them to one abstract program builder;
- leaves all TypeScript syntax emission to a future concrete subclass.

The abstract hooks cover only syntax nodes reachable in the current Core IR: constants, compound terms, list terms, assertions, and connective formulas. `Concept` and `Operator` remain catalog-owned metadata carried by those nodes, so they do not receive speculative standalone declaration hooks.

## Scope

Files in scope:

- `examples/haitun-workspace/skills/fusion-flow-next/src/generator.ts`
- `examples/haitun-workspace/skills/fusion-flow-next/test/compiler-contract.ts`
- `examples/haitun-workspace/skills/fusion-flow-next/README.md`

Explicitly out of scope:

- BNF or generated parser changes;
- checker implementation;
- concrete TypeScript output;
- compiler registries, multiple backends, execution, or runtime integration;
- new dependencies or package exports.

## Verification

The contract test defines a minimal concrete subclass, proving that all hooks compose against the existing Core IR and `GenerateResult` types. `npm run typecheck` remains the package's runnable contract check.
