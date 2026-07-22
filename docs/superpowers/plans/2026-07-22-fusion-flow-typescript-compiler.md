# FusionFlow TypeScript Compiler Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a TypeScript-specific abstract compiler template over the existing FusionFlow Workflow Core IR.

**Architecture:** Keep the boundary in `src/generator.ts`. A concrete template method handles checker gating and Core IR union dispatch, while abstract hooks own all future TypeScript syntax emission.

**Tech Stack:** TypeScript, NodeNext modules, existing `tsc --noEmit` contract checks.

---

### Task 1: Add the compiler template contract

**Files:**
- Modify: `examples/haitun-workspace/skills/fusion-flow-next/src/generator.ts`
- Create: `examples/haitun-workspace/skills/fusion-flow-next/test/compiler-contract.ts`
- Modify: `examples/haitun-workspace/skills/fusion-flow-next/README.md`

- [ ] **Step 1: Write the failing compiler contract**

Create `test/compiler-contract.ts` with a concrete recording subclass:

```ts
import {
  Assertion,
  CompoundTerm,
  ConnectiveFormula,
  Constant,
  type Formula,
  ListTerm,
  Operator,
  type Term,
  Workflow,
} from "../src/core-ir.js";
import { TypeScriptCompiler } from "../src/generator.js";
import type { GenerateResult } from "../src/types.js";

class RecordingCompiler extends TypeScriptCompiler {
  protected compileConstant(constant: Constant): string {
    return constant.symbol;
  }

  protected compileCompoundTerm(term: CompoundTerm): string {
    return `${term.operator.name}(${term.arguments.map((argument) => this.compileTerm(argument)).join(", ")})`;
  }

  protected compileListTerm(term: ListTerm): string {
    return `[${term.items.map((item) => this.compileTerm(item)).join(", ")}]`;
  }

  protected compileAssertion(assertion: Assertion): string {
    return `${this.compileTerm(assertion.lhs)} ${assertion.relationSymbol} ${this.compileTerm(assertion.rhs)}`;
  }

  protected compileConnectiveFormula(formula: ConnectiveFormula): string {
    const right = formula.formulaRight === null ? "" : ` ${this.compileFormula(formula.formulaRight)}`;
    return `${formula.connective} ${this.compileFormula(formula.formulaLeft)}${right}`;
  }

  protected buildProgram(workflow: Workflow, assertions: readonly string[]): GenerateResult {
    return { code: `${workflow.name}:${assertions.join(";")}`, diagnostics: [] };
  }

  public compileTermForContract(term: Term): string {
    return this.compileTerm(term);
  }

  public compileFormulaForContract(formula: Formula): string {
    return this.compileFormula(formula);
  }
}

const value = new Constant("value", []);
const operator = new Operator("identity");
const assertion = new Assertion(new CompoundTerm(operator, [value]), new ListTerm([value]));
const compiler = new RecordingCompiler();
const result = compiler.compile({
  coreIR: new Workflow("example", [assertion]),
  diagnostics: [],
  canGenerate: true,
});

const code: string | null = result.code;
const term: string = compiler.compileTermForContract(value);
const formula: string = compiler.compileFormulaForContract(assertion);
void [code, term, formula];
```

- [ ] **Step 2: Run the contract to verify it fails**

Run from `examples/haitun-workspace/skills/fusion-flow-next`:

```bash
rtk npm run typecheck
```

Expected: failure because `src/generator.ts` does not export `TypeScriptCompiler`.

- [ ] **Step 3: Implement the minimal compiler template**

Replace the placeholder in `src/generator.ts` with:

```ts
import {
  Assertion,
  CompoundTerm,
  ConnectiveFormula,
  Constant,
  type Formula,
  ListTerm,
  type Term,
  type Workflow,
} from "./core-ir.js";
import type { CheckResult, GenerateResult } from "./types.js";

export abstract class TypeScriptCompiler {
  public compile(checkResult: CheckResult): GenerateResult {
    if (!checkResult.canGenerate) {
      return { code: null, diagnostics: [] };
    }

    const workflow = checkResult.coreIR;
    return this.buildProgram(
      workflow,
      workflow.assertions.map((assertion) => this.compileAssertion(assertion)),
    );
  }

  protected compileFormula(formula: Formula): string {
    if (formula instanceof Assertion) {
      return this.compileAssertion(formula);
    }
    if (formula instanceof ConnectiveFormula) {
      return this.compileConnectiveFormula(formula);
    }
    return this.unsupported("formula", formula);
  }

  protected compileTerm(term: Term): string {
    if (term instanceof Constant) {
      return this.compileConstant(term);
    }
    if (term instanceof CompoundTerm) {
      return this.compileCompoundTerm(term);
    }
    if (term instanceof ListTerm) {
      return this.compileListTerm(term);
    }
    return this.unsupported("term", term);
  }

  protected abstract compileConstant(constant: Constant): string;
  protected abstract compileCompoundTerm(term: CompoundTerm): string;
  protected abstract compileListTerm(term: ListTerm): string;
  protected abstract compileAssertion(assertion: Assertion): string;
  protected abstract compileConnectiveFormula(formula: ConnectiveFormula): string;
  protected abstract buildProgram(workflow: Workflow, assertions: readonly string[]): GenerateResult;

  private unsupported(label: string, node: unknown): never {
    const nodeType = node instanceof Object ? node.constructor.name : typeof node;
    throw new TypeError(`${this.constructor.name} cannot compile unsupported ${label} node of type ${nodeType}.`);
  }
}
```

- [ ] **Step 4: Run the focused package verification**

Run:

```bash
rtk npm run typecheck
```

Expected: exit 0.

- [ ] **Step 5: Synchronize the package documentation**

Update `README.md` so `src/generator.ts` describes the abstract compiler template, and state that concrete TypeScript emission remains unimplemented.

- [ ] **Step 6: Verify the complete diff**

Run from the repository root:

```bash
rtk npm run typecheck --prefix examples/haitun-workspace/skills/fusion-flow-next
rtk git diff --check
```

Expected: both commands exit 0.

- [ ] **Step 7: Commit**

```bash
git add docs/superpowers/specs/2026-07-22-fusion-flow-typescript-compiler-design.md docs/superpowers/plans/2026-07-22-fusion-flow-typescript-compiler.md examples/haitun-workspace/skills/fusion-flow-next/src/generator.ts examples/haitun-workspace/skills/fusion-flow-next/test/compiler-contract.ts examples/haitun-workspace/skills/fusion-flow-next/README.md
git commit -m "feat(fusion-flow-next): scaffold TypeScript compiler"
```
