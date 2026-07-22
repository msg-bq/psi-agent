import assert from "node:assert/strict";

import {
  Assertion,
  CompoundTerm,
  ConnectiveFormula,
  Constant,
  IfTerm,
  ListTerm,
  WorkflowFile,
} from "../.test-build/src/core-ir.js";
import { parseWorkflow } from "../.test-build/src/parser.js";

const result = parseWorkflow(`
  const review: Step, Agent;
  const "draft": Artifact;
  const backup: Agent;

  workflow first {
    custom(agent, review) == TRUE;
    custom(review) == False;
  }

  workflow second {
    step_executor(review) == if(!(max_attempts(review) != 2) AND max_turns(agent) = 8, writer, human);
    custom(1 + 2 * 3, [review, "draft"], -(4 ^ 2 ^ 3)) == true;
  }
`);

assert.deepEqual(result.diagnostics, []);
assert.ok(result.coreIR instanceof WorkflowFile);
const file = result.coreIR;
assert.deepEqual(
  file.constants.map(({ symbol }) => symbol),
  ["review", "draft", "backup"],
  "declarations retain source order and quoted delimiters are stripped",
);
assert.deepEqual(
  file.workflows.map(({ name }) => name),
  ["first", "second"],
  "workflows retain source order",
);

const [review, draft, backup] = file.constants;
assert.ok(review instanceof Constant);
assert.ok(draft instanceof Constant);
assert.ok(backup instanceof Constant);
assert.equal(
  review.belongConcepts[1],
  backup.belongConcepts[0],
  "declared concepts are reused parse-locally",
);

const [firstWorkflow, secondWorkflow] = file.workflows;
const [firstCustomAssertion, secondCustomAssertion] = firstWorkflow.assertions;
const [conditionalAssertion, arithmeticAssertion] = secondWorkflow.assertions;
for (const assertion of [
  firstCustomAssertion,
  secondCustomAssertion,
  conditionalAssertion,
  arithmeticAssertion,
]) {
  assert.ok(assertion instanceof Assertion);
  assert.equal(assertion.relationSymbol, "=", "top-level == normalizes to =");
}

assert.ok(firstCustomAssertion.lhs instanceof CompoundTerm);
assert.ok(secondCustomAssertion.lhs instanceof CompoundTerm);
assert.ok(arithmeticAssertion.lhs instanceof CompoundTerm);
const firstCustom = firstCustomAssertion.lhs;
const secondCustom = secondCustomAssertion.lhs;
const arithmeticCall = arithmeticAssertion.lhs;
assert.equal(firstCustom.operator.name, "custom");
assert.equal(firstCustom.operator, secondCustom.operator);
assert.equal(firstCustom.operator, arithmeticCall.operator, "named operators are reused");
assert.equal(firstCustom.arguments[1], review, "declared constants are reused");
assert.equal(secondCustom.arguments[0], review);
assert.equal(firstCustomAssertion.rhs.symbol, "true");
assert.equal(secondCustomAssertion.rhs.symbol, "false");
assert.equal(
  arithmeticAssertion.rhs,
  firstCustomAssertion.rhs,
  "booleans normalize before parse-local reuse",
);

assert.ok(conditionalAssertion.lhs instanceof CompoundTerm);
assert.equal(conditionalAssertion.lhs.operator.name, "step_executor");
assert.equal(conditionalAssertion.lhs.arguments[0], review);
assert.ok(conditionalAssertion.rhs instanceof IfTerm);
const conditional = conditionalAssertion.rhs;
assert.ok(conditional.condition instanceof ConnectiveFormula);
assert.equal(conditional.condition.connective, "AND");
assert.ok(conditional.condition.formulaLeft instanceof ConnectiveFormula);
assert.equal(conditional.condition.formulaLeft.connective, "NOT");
assert.equal(conditional.condition.formulaLeft.formulaRight, null);
assert.ok(conditional.condition.formulaLeft.formulaLeft instanceof Assertion);
const notEquals = conditional.condition.formulaLeft.formulaLeft;
assert.equal(notEquals.relationSymbol, "!=");
assert.ok(notEquals.lhs instanceof CompoundTerm);
assert.equal(notEquals.lhs.operator.name, "max_attempts");
assert.equal(notEquals.lhs.arguments[0], review);
assert.equal(notEquals.rhs.symbol, "2");
assert.ok(conditional.condition.formulaRight instanceof Assertion);
const numericEquals = conditional.condition.formulaRight;
assert.equal(numericEquals.relationSymbol, "=");
assert.ok(numericEquals.lhs instanceof CompoundTerm);
assert.equal(numericEquals.lhs.operator.name, "max_turns");
assert.equal(
  numericEquals.lhs.arguments[0],
  firstCustom.arguments[0],
  "undeclared constants are reused parse-locally",
);
assert.equal(numericEquals.rhs.symbol, "8");
assert.equal(conditional.whenTrue.symbol, "writer");
assert.equal(conditional.whenFalse.symbol, "human");

const [sum, list, negation] = arithmeticCall.arguments;
assert.ok(sum instanceof CompoundTerm);
assert.equal(sum.operator.name, "+");
assert.equal(sum.arguments[0].symbol, "1");
assert.ok(sum.arguments[1] instanceof CompoundTerm);
assert.equal(sum.arguments[1].operator.name, "*");
assert.deepEqual(
  sum.arguments[1].arguments.map(({ symbol }) => symbol),
  ["2", "3"],
  "multiplication binds tighter than addition",
);
assert.ok(list instanceof ListTerm);
assert.equal(list.items[0], review);
assert.equal(list.items[1], draft);
assert.ok(negation instanceof CompoundTerm);
assert.equal(negation.operator.name, "-");
assert.equal(negation.arguments.length, 1, "unary minus has one operand");
assert.ok(negation.arguments[0] instanceof CompoundTerm);
const power = negation.arguments[0];
assert.equal(power.operator.name, "^");
assert.equal(power.arguments[0].symbol, "4");
assert.ok(power.arguments[1] instanceof CompoundTerm);
assert.equal(power.arguments[1].operator.name, "^");
assert.deepEqual(
  power.arguments[1].arguments.map(({ symbol }) => symbol),
  ["2", "3"],
  "power is right-associative",
);

const duplicate = parseWorkflow(`
  const item: First;
  const item: Second;
  workflow duplicate { custom(item) == true; }
`);
assert.deepEqual(duplicate.diagnostics, []);
assert.ok(duplicate.coreIR instanceof WorkflowFile);
assert.deepEqual(
  duplicate.coreIR.constants.map(({ symbol }) => symbol),
  ["item", "item"],
  "duplicate declarations are retained",
);
assert.notEqual(duplicate.coreIR.constants[0], duplicate.coreIR.constants[1]);
assert.equal(
  duplicate.coreIR.workflows[0].assertions[0].lhs.arguments[0],
  duplicate.coreIR.constants[0],
  "term lookup uses the first duplicate declaration",
);

const malformed = parseWorkflow(
  "workflow broken { custom(value) = true; }",
);
assert.equal(malformed.coreIR, null, "syntax errors produce no Core IR");
assert.ok(malformed.diagnostics.length > 0, "syntax errors produce diagnostics");
assert.equal(malformed.diagnostics[0].severity, "error");
assert.ok(malformed.diagnostics[0].message.length > 0);
assert.deepEqual(
  malformed.diagnostics[0].span,
  {
    start: { line: 1, column: 33 },
    end: { line: 1, column: 34 },
  },
  "diagnostic columns are 1-based and spans are one-token half-open",
);

const truncated = parseWorkflow(
  "workflow broken { custom(value) == true;",
);
assert.equal(truncated.coreIR, null, "EOF syntax errors produce no Core IR");
assert.ok(truncated.diagnostics.length > 0, "EOF syntax errors produce diagnostics");
const eofSpan = truncated.diagnostics[0].span;
assert.equal(
  eofSpan.end.column,
  eofSpan.start.column + 1,
  "EOF diagnostics use a visible one-token half-open span",
);

console.log("parser runtime contract: ok");
