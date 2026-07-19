/**
 * A source location.
 *
 * Both line and column are 1-based. Public diagnostics deliberately omit
 * character offsets to avoid UTF-16/UTF-32 ambiguity.
 */
export interface SourcePosition {
  readonly line: number;
  readonly column: number;
}

export interface SourceSpan {
  readonly start: SourcePosition;
  /** Exclusive end position; spans use the half-open interval `[start, end)`. */
  readonly end: SourcePosition;
}

export type DiagnosticSeverity = "error" | "warning";

export interface Diagnostic {
  readonly severity: DiagnosticSeverity;
  readonly message: string;
  readonly span?: SourceSpan;
  /** An identifier from the language design review such as S01; never a diagnostic code, URL, or source span. */
  readonly designReference?: string;
}

export interface IdentifierNode {
  readonly kind: "identifier";
  readonly name: string;
  readonly span: SourceSpan;
}

export interface BooleanLiteralNode {
  readonly kind: "boolean";
  readonly value: boolean;
  readonly span: SourceSpan;
}

/** An ordered list of workflow values. */
export interface ListLiteralNode {
  readonly kind: "list";
  readonly items: readonly WorkflowValue[];
  readonly span: SourceSpan;
}

export type WorkflowValue = IdentifierNode | BooleanLiteralNode | ListLiteralNode;

export interface OperatorCallNode {
  readonly kind: "operatorCall";
  readonly operator: IdentifierNode;
  readonly arguments: readonly WorkflowValue[];
  readonly span: SourceSpan;
}

/** `=` is canonical; the parser may accept `==` but must normalize it to `=` before building the AST. */
export interface AssertionNode {
  readonly kind: "assertion";
  readonly left: OperatorCallNode;
  readonly comparator: "=";
  readonly right: WorkflowValue;
  readonly span: SourceSpan;
}

/** The root node for one workflow source file. */
export interface WorkflowAst {
  readonly kind: "workflow";
  readonly name: IdentifierNode;
  readonly statements: readonly AssertionNode[];
  readonly span: SourceSpan;
}

export interface ParseResult {
  /** Non-null exactly when this phase produced no error diagnostics. */
  readonly workflow: WorkflowAst | null;
  /** Parser diagnostics only; callers combine phase results when needed. */
  readonly diagnostics: readonly Diagnostic[];
}

/**
 * The checker only receives a non-null WorkflowAst from a successful parse;
 * parse failures never produce CheckResult.
 */
export interface CheckResult {
  readonly workflow: WorkflowAst;
  /** Checker diagnostics only; parser diagnostics are not repeated here. */
  readonly diagnostics: readonly Diagnostic[];
  /**
   * True exactly when there are no checker errors and exact TypeScript lowering
   * is supported.
   */
  readonly canGenerate: boolean;
}

/**
 * Non-null `code` means generation succeeded and may coexist with warning
 * diagnostics. Any error diagnostic requires `code: null`.
 */
export interface GenerateResult {
  /** Null means no TypeScript; the generator must never emit placeholder or approximate code. */
  readonly code: string | null;
  /** Generator diagnostics only; parser and checker diagnostics are not repeated here. */
  readonly diagnostics: readonly Diagnostic[];
}
