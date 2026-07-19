import type { Diagnostic } from "./types.js";

/** A planned syntax or action mapping. */
export interface PlannedMapping {
  readonly description: string;
  /**
   * `null` explicitly means the planner could not find a matching syntax or
   * action; it must not invent a name. A non-null name must be non-empty after
   * trimming. Empty or whitespace-only names are invalid, and the future
   * checker treats them as unmapped.
   */
  readonly name: string | null;
}

export interface PlannedFunction {
  readonly id: string;
  readonly description: string;
  /**
   * Must contain at least one mapping. Empty means invalid or incomplete
   * planner output; the future checker warns and sets `canAuthorWorkflow` to
   * false.
   */
  readonly syntax: readonly PlannedMapping[];
  /**
   * Empty explicitly means no external action is required. If an action is
   * required but unmapped, include a `PlannedMapping` with `name: null`; do not
   * omit it.
   */
  readonly actions: readonly PlannedMapping[];
}

export interface PlanningCheckResult {
  /**
   * Means only that the declared planned functions have acceptable mappings.
   * It does not imply DSL parse validity, backend lowering, runtime tool
   * availability or authorization, or successful execution.
   */
  readonly canAuthorWorkflow: boolean;
  readonly diagnostics: readonly Diagnostic[];
}

/**
 * Haitun must call this after listing planned functions and before authoring the
 * DSL.
 *
 * A future implementation will emit warnings for null or unknown mappings and
 * set `canAuthorWorkflow` to false. It only checks declared items and cannot
 * prove that the LLM listed every required function. It does not inspect
 * runtime tool authorization or execute anything. The future checker validates
 * the sentinel rules documented by these interfaces. The current implementation
 * throws only because this module is not wired or implemented; a future missing
 * mapping is a normal result, not an exception.
 */
export function checkPlannedFunctions(
  functions: readonly PlannedFunction[],
): PlanningCheckResult {
  void functions;
  throw new Error("FusionFlow Next planning check is not implemented.");
}
