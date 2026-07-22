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

/** Shared Core IR traversal for concrete TypeScript emitters. */
export abstract class TypeScriptCompiler {
  public compile(checkResult: CheckResult): GenerateResult {
    if (!checkResult.canGenerate) {
      return { code: null, diagnostics: [] };
    }

    const workflow = checkResult.coreIR;
    return this.buildProgram(
      workflow,
      workflow.assertions.map((assertion) =>
        this.compileAssertion(assertion),
      ),
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

  protected abstract compileConnectiveFormula(
    formula: ConnectiveFormula,
  ): string;

  protected abstract buildProgram(
    workflow: Workflow,
    assertions: readonly string[],
  ): GenerateResult;

  private unsupported(label: string, node: unknown): never {
    const nodeType =
      node instanceof Object ? node.constructor.name : typeof node;
    throw new TypeError(
      `${this.constructor.name} cannot compile unsupported ${label} node of type ${nodeType}.`,
    );
  }
}
