# FusionFlow Next

FusionFlow Next is a temporary name for an isolated compiler-architecture package.
This directory intentionally has no `SKILL.md`, so Haitun will not auto-load it.
Existing `fusion-flow` and `.flow.ts` paths remain unchanged.
This PR only establishes compiler architecture contracts.

## Modules

- `grammar/FusionFlow.g4`: syntax only.
- `src/types.ts`: shared AST, diagnostics, and results.
- `src/parser.ts`: parse boundary.
- `src/checker.ts`: static semantics and exact-lowering gate.
- `src/generator.ts`: checked workflow to deterministic TypeScript boundary.
- `src/planning.ts`: Haitun lists planned functions first and checks for missing mappings.

## Activation boundary

Do not add a `SKILL.md`, workspace tools, a prompt switch, or runner changes until the parser, checker, and generator have real implementations and runnable checks.

Integrate in this order: generated parser -> real functions and checks -> inactive or opt-in Haitun checker tool -> prompt opt-in -> replace legacy only after migration is complete. Existing `fusion-flow` remains the source of truth until the final migration.
