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
    const right =
      formula.formulaRight === null
        ? ""
        : ` ${this.compileFormula(formula.formulaRight)}`;
    return `${formula.connective} ${this.compileFormula(formula.formulaLeft)}${right}`;
  }

  protected buildProgram(
    workflow: Workflow,
    assertions: readonly string[],
  ): GenerateResult {
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
const assertion = new Assertion(
  new CompoundTerm(operator, [value]),
  new ListTerm([value]),
);
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
