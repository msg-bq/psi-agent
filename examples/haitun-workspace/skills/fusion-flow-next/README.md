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

## Suggested work split

1. **Language contract** owns `grammar/FusionFlow.g4` and `src/types.ts`: define the supported syntax and shared AST, including constructs that cannot yet be lowered exactly to the current runtime.
2. **Parser** owns `generated/` and `src/parser.ts`: generate the parser, report syntax errors, and convert parser output into the shared AST.
3. **Static checker** owns `src/checker.ts`: check workflow legality and reject constructs that cannot be lowered without changing meaning.
4. **TypeScript generator** owns `src/generator.ts`: convert a checked workflow into deterministic TypeScript and refuse unsupported input.
5. **Planning warnings** owns `src/planning.ts`: check the functions listed by Haitun and warn when a syntax or action mapping is missing.
6. **Haitun integration** updates existing prompt and tool entry points only after parsing and checks work: add the syntax-check tool and require planning before workflow generation.
7. **Compatibility and migration** owns runnable checks under `test/` and the activation gate: keep the existing `fusion-flow`, runner, and `.flow.ts` path unchanged until final migration.

Dependency order: 1 -> 2 -> 3 -> 4; 1 -> 5; 3 + 4 + 5 -> 6. Workstream 7 runs throughout and gates activation.
