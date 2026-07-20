import type { ParseResult } from "./types.js";

/**
 * Future implementation invokes the committed ANTLR-generated lexer and parser,
 * collects syntax diagnostics, and lowers the parse tree directly into
 * KEDispatcher-aligned Workflow Core IR. Accepted `==` spelling is normalized
 * to canonical `=` during lowering. This boundary does not perform static
 * workflow semantics or TypeScript backend checks. Generated imports are
 * deliberately deferred until generated sources are committed.
 */
export function parseWorkflow(source: string): ParseResult {
  void source;
  throw new Error("FusionFlow Next parser is not implemented.");
}
