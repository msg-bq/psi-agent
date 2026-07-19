import type { CheckResult, WorkflowAst } from "./types.js";

/**
 * Checks a successfully parsed AST. The current stub throws only because the
 * checker implementation is unavailable. Once implemented, ordinary workflow
 * errors and lowering diagnostics are returned in the CheckResult diagnostics
 * list rather than thrown.
 *
 * Future implementations own static workflow semantics such as operator
 * contracts and arity, enclosing-workflow identity references, duplicates,
 * and reference integrity. For TypeScript lowering, the checker only answers
 * whether lossless/exact lowering exists; it does not build, rewrite, or
 * approximate emitter shapes.
 *
 * This boundary must not parse source, emit TypeScript, or execute workflows.
 */
export function checkWorkflow(workflow: WorkflowAst): CheckResult {
  void workflow;
  throw new Error("FusionFlow Next checker is not implemented.");
}
