import type { ParseResult } from "./types.js";

/**
 * Future implementation invokes the committed ANTLR-generated lexer and parser,
 * collects syntax diagnostics, builds an AST from the CST, and normalizes the
 * accepted `==` spelling to canonical `=` before AST construction. It does not
 * perform static workflow semantics or TypeScript backend checks. Generated
 * imports are deliberately deferred until generated sources are committed.
 */
export function parseWorkflow(source: string): ParseResult {
  void source;
  throw new Error("FusionFlow Next parser is not implemented.");
}
