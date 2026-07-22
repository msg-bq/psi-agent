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
  type Term,
  Workflow,
  WorkflowFile,
} from "../src/core-ir.js";
import type { ParseResult } from "../src/types.js";

// @ts-expect-error Workflow Core IR deliberately has no variables.
import type { Variable } from "../src/core-ir.js";
// @ts-expect-error Workflow Core IR deliberately has no rule/request layer.
import type { Rule } from "../src/core-ir.js";

const stepConcept = new Concept("Step");
const artifactConcept = new Concept("Artifact");
const listConcept = new Concept("List");
const integerConcept = new Concept("Integer");

const reviewStep = new Constant("review_step", [stepConcept]);
const draft = new Constant("draft", [artifactConcept]);
const report = new Constant("report", [artifactConcept]);
const age = new Constant("age", [integerConcept]);

const consumesMulti = new Operator(
  "consumes_multi",
  [stepConcept],
  listConcept,
);
const artifacts = new ListTerm([draft, report]);
const consumes = new Assertion(
  new CompoundTerm(consumesMulti, [reviewStep]),
  artifacts,
);
const adult = new Assertion(age, new Constant("20", [integerConcept]), ">");
const senior = new Assertion(age, new Constant("40", [integerConcept]), ">");
const condition = new ConnectiveFormula(
  adult,
  "AND",
  new ConnectiveFormula(senior, "NOT"),
);
const conditionalArtifact = new IfTerm(condition, draft, report);
const workflow = new Workflow("review_pipeline", [consumes]);
const workflowFile = new WorkflowFile(
  [reviewStep, draft, report, age],
  [workflow],
);
const parseResult: ParseResult = { coreIR: workflowFile, diagnostics: [] };

if (false) {
  // @ts-expect-error AND requires a right formula.
  new ConnectiveFormula(adult, "AND");
  // @ts-expect-error NOT cannot have a right formula.
  new ConnectiveFormula(adult, "NOT", senior);
}

const workflowName: string = workflow.name;
const firstListItem: Term = artifacts.items[0]!;
const retainedConditionalTerm: Term = conditionalArtifact;
const retainedCondition: Formula = condition;
const retainedAssertion: Assertion = workflow.assertions[0]!;
const catalogArity: number = consumesMulti.arity;

void [
  workflow,
  workflowName,
  firstListItem,
  retainedConditionalTerm,
  retainedCondition,
  retainedAssertion,
  catalogArity,
  parseResult,
];

void (null as unknown as Variable);
void (null as unknown as Rule);
