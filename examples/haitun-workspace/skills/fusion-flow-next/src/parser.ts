import {
  BaseErrorListener,
  CharStream,
  CommonTokenStream,
  Token,
} from "antlr4ng";
import type {
  ATNSimulator,
  RecognitionException,
  Recognizer,
} from "antlr4ng";

import { FusionFlowLexer } from "../generated/FusionFlowLexer.js";
import {
  type AssertionContext,
  type AtomicTermContext,
  type ComparisonContext,
  type ConstDeclContext,
  type FormulaContext,
  FusionFlowParser,
  type IfExpressionContext,
  type ListLiteralContext,
  type TermContext,
  type WorkflowDeclContext,
  type WorkflowFileContext,
} from "../generated/FusionFlowParser.js";
import { FusionFlowVisitor } from "../generated/FusionFlowVisitor.js";
import {
  Assertion,
  CompoundTerm,
  Concept,
  ConnectiveFormula,
  Constant,
  type Formula,
  IfTerm,
  ListTerm,
  Operator,
  type RelationSymbol,
  type Term,
  Workflow,
  WorkflowFile,
} from "./core-ir.js";
import type { Diagnostic, ParseResult } from "./types.js";

class DiagnosticListener extends BaseErrorListener {
  readonly diagnostics: Diagnostic[] = [];

  public override syntaxError<S extends Token, T extends ATNSimulator>(
    _recognizer: Recognizer<T>,
    offendingSymbol: S | null,
    line: number,
    column: number,
    message: string,
    _error: RecognitionException | null,
  ): void {
    const width =
      offendingSymbol?.type === Token.EOF
        ? 1
        : Math.max(offendingSymbol?.text?.length ?? 1, 1);
    const startColumn = column + 1;
    this.diagnostics.push({
      severity: "error",
      message,
      span: {
        start: { line, column: startColumn },
        end: { line, column: startColumn + width },
      },
    });
  }
}

type LoweredNode = WorkflowFile | Workflow | Formula | Term;

/** Parse-tree lowering mirrors KEDispatcher's handwritten visitor. */
class CoreIrVisitor extends FusionFlowVisitor<LoweredNode> {
  private readonly concepts = new Map<string, Concept>();
  private readonly constants = new Map<string, Constant>();
  private readonly operators = new Map<string, Operator>();

  public override visitWorkflowFile = (
    context: WorkflowFileContext,
  ): WorkflowFile => {
    const constants = context
      .constDecl()
      .map((declaration) => this.visitConstDecl(declaration));
    const workflows = context
      .workflowDecl()
      .map((workflow) => this.visitWorkflowDecl(workflow));
    return new WorkflowFile(constants, workflows);
  };

  public override visitConstDecl = (context: ConstDeclContext): Constant => {
    const symbol = this.normalizeConstant(context.constantName().getText());
    const concepts = context
      .conceptNameList()
      .conceptName()
      .map((concept) => this.resolveConcept(concept.getText()));
    const constant = new Constant(symbol, concepts);
    if (!this.constants.has(symbol)) {
      this.constants.set(symbol, constant);
    }
    return constant;
  };

  public override visitWorkflowDecl = (
    context: WorkflowDeclContext,
  ): Workflow =>
    new Workflow(
      context.workflowName().getText(),
      context
        .workflowItem()
        .map((item) => this.visitAssertion(item.assertion())),
    );

  public override visitAssertion = (
    context: AssertionContext,
  ): Assertion => {
    const terms = context.term();
    return new Assertion(
      this.visitTerm(terms[0]),
      this.visitTerm(terms[1]),
      "=",
    );
  };

  public override visitFormula = (context: FormulaContext): Formula => {
    const comparison = context.comparison();
    if (comparison !== null) {
      return this.visitComparison(comparison);
    }
    if (context.NOT() !== null) {
      return new ConnectiveFormula(
        this.visitFormula(context.formula(0)!),
        "NOT",
      );
    }
    if (context._left !== undefined && context._right !== undefined) {
      return new ConnectiveFormula(
        this.visitFormula(context._left),
        context.AND() === null ? "OR" : "AND",
        this.visitFormula(context._right),
      );
    }
    return this.visitFormula(context.formula(0)!);
  };

  public override visitComparison = (
    context: ComparisonContext,
  ): Assertion => {
    const terms = context.term();
    return new Assertion(
      this.visitTerm(terms[0]),
      this.visitTerm(terms[1]),
      context.comparisonOp().getText() as RelationSymbol,
    );
  };

  public override visitTerm = (context: TermContext): Term => {
    if (context._left !== undefined && context._right !== undefined) {
      return new CompoundTerm(this.resolveOperator(context._op!.text!), [
        this.visitTerm(context._left),
        this.visitTerm(context._right),
      ]);
    }

    if (context._op !== undefined && context._op !== null) {
      const operand = this.visitTerm(context.term(0)!);
      return context._op.text === "+"
        ? operand
        : new CompoundTerm(this.resolveOperator("-"), [operand]);
    }

    const conditional = context.ifExpression();
    if (conditional !== null) {
      return this.visitIfExpression(conditional);
    }

    const operatorName = context.operatorName();
    if (operatorName !== null) {
      const arguments_ =
        context.termList()?.term().map((term) => this.visitTerm(term)) ?? [];
      return new CompoundTerm(
        this.resolveOperator(operatorName.getText()),
        arguments_,
      );
    }

    const list = context.listLiteral();
    if (list !== null) {
      return this.visitListLiteral(list);
    }

    const atomic = context.atomicTerm();
    if (atomic !== null) {
      return this.visitAtomicTerm(atomic);
    }

    return this.visitTerm(context.term(0)!);
  };

  public override visitIfExpression = (
    context: IfExpressionContext,
  ): IfTerm => {
    const branches = context.term();
    return new IfTerm(
      this.visitFormula(context.formula()),
      this.visitTerm(branches[0]),
      this.visitTerm(branches[1]),
    );
  };

  public override visitListLiteral = (
    context: ListLiteralContext,
  ): ListTerm =>
    new ListTerm(
      context.termList()?.term().map((term) => this.visitTerm(term)) ?? [],
    );

  public override visitAtomicTerm = (
    context: AtomicTermContext,
  ): Constant => {
    const symbol = this.normalizeConstant(context.getText());
    const existing = this.constants.get(symbol);
    if (existing !== undefined) {
      return existing;
    }
    const constant = new Constant(symbol, []);
    this.constants.set(symbol, constant);
    return constant;
  };

  private resolveConcept(name: string): Concept {
    const existing = this.concepts.get(name);
    if (existing !== undefined) {
      return existing;
    }
    const concept = new Concept(name);
    this.concepts.set(name, concept);
    return concept;
  }

  private resolveOperator(name: string): Operator {
    const existing = this.operators.get(name);
    if (existing !== undefined) {
      return existing;
    }
    const operator = new Operator(name);
    this.operators.set(name, operator);
    return operator;
  }

  private normalizeConstant(symbol: string): string {
    if (symbol.startsWith('"') && symbol.endsWith('"')) {
      return symbol.slice(1, -1);
    }
    const normalized = symbol.toLowerCase();
    return normalized === "true" || normalized === "false"
      ? normalized
      : symbol;
  }
}

export function parseWorkflow(source: string): ParseResult {
  const listener = new DiagnosticListener();
  const lexer = new FusionFlowLexer(CharStream.fromString(source));
  lexer.removeErrorListeners();
  lexer.addErrorListener(listener);

  const parser = new FusionFlowParser(new CommonTokenStream(lexer));
  parser.removeErrorListeners();
  parser.addErrorListener(listener);
  const tree = parser.workflowFile();

  if (listener.diagnostics.length > 0) {
    return { coreIR: null, diagnostics: listener.diagnostics };
  }
  return {
    coreIR: new CoreIrVisitor().visitWorkflowFile(tree),
    diagnostics: listener.diagnostics,
  };
}
