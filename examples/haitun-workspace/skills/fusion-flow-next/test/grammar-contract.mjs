import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
assert.deepEqual(
  readdirSync(join(root, "grammar")).filter((name) => name.endsWith(".g4")),
  ["FusionFlow.g4"],
  "the language contract must have one grammar",
);
const grammarPath = join(root, "grammar", "FusionFlow.g4");
const examplePath = join(root, "examples", "operator-catalog.workflow");
const grammar = readFileSync(grammarPath, "utf8");
const example = readFileSync(examplePath, "utf8");

const operatorCategories = {
  workflowOwnerOperator: {
    input_workflow: 2,
    input_workflow_multi: 1,
    output_workflow: 2,
    output_workflow_multi: 1,
    max_concurrency: 1,
    workflow_timeout: 1,
  },
  stepOwnerOperator: {
    step_name: 1,
    step_instruction: 1,
    step_executor: 1,
    step_timeout: 1,
    max_attempts: 1,
  },
  dataResourceOperator: {
    consumes: 2,
    consumes_multi: 1,
    produces: 2,
    produces_multi: 1,
    foreach_item: 2,
    resource_requirement: 2,
  },
  agentOwnerOperator: {
    agent_config: 4,
    allowed_tool: 2,
    max_output_tokens: 1,
    temperature: 1,
    reasoning_effort: 1,
    max_turns: 1,
  },
};

function ruleBody(grammar, name) {
  const match = grammar.match(new RegExp("\\b" + name + "\\s*:(.*?);", "s"));
  assert.ok(match, "missing " + name + " rule");
  return match[1];
}

for (const [category, operators] of Object.entries(operatorCategories)) {
  const body = ruleBody(grammar, category);
  assert.deepEqual(
    [...body.matchAll(/'([a-z_]+)'/g)].map((match) => match[1]).sort(),
    Object.keys(operators).sort(),
    category + " must contain exactly its declared operators",
  );

  for (const operator of Object.keys(operators)) {
    assert.match(example, new RegExp("\\b" + operator + "\\s*\\("));
  }
}

assert.deepEqual(
  ruleBody(grammar, "workflowBuiltinOperator").match(/\b[a-z]\w+Operator\b/g),
  Object.keys(operatorCategories),
  "builtin dispatch must contain exactly the four owner categories",
);
assert.match(ruleBody(grammar, "operatorName"), /LOWID\s*\|\s*workflowBuiltinOperator/s);

assert.match(
  grammar,
  /ifExpression\s*:\s*IF\s+LPAREN\s+formula\s+COMMA\s+term\s+COMMA\s+term\s+RPAREN\s*;/s,
);
assert.doesNotMatch(grammar, /\bELSE\b|\bbranch(?:Stmt|Arm)\b/);
assert.match(ruleBody(grammar, "workflowFile"), /^\s*\(constDecl SEMICOLON\)\* workflowDecl\+ EOF\s*$/s);
assert.match(ruleBody(grammar, "workflowItem"), /^\s*assertion SEMICOLON\s*$/s);
assert.match(ruleBody(grammar, "assertion"), /^\s*term EQUALITY term\s*$/s);
assert.match(
  ruleBody(grammar, "atomicTerm"),
  /^\s*constantName\s*\|\s*booleanLiteral\s*$/s,
);
for (const removedRule of [
  "declaration",
  "conceptDecl",
  "opDecl",
  "consumesMultiAssertion",
  "artifactSet",
  "variableName",
  "callableWorkflowBuiltinOperator",
  "surfaceOnlyOperator",
]) {
  assert.doesNotMatch(grammar, new RegExp("\\b" + removedRule + "\\s*:"));
}
assert.doesNotMatch(grammar, /\b(?:CONCEPT|OP|IMPLIES|IFF|ARROW)\s*:/);
assert.match(grammar, /\bNOT\s*:\s*'!'\s*;/);

if (process.argv.includes("--source-only")) {
  console.log("grammar source contract: ok");
  process.exit(0);
}

const { CharStream, CommonTokenStream } = await import("antlr4ng");
const generated = join(root, "generated", "test-build", "generated");
const [{ FusionFlowLexer }, { FusionFlowParser }] = await Promise.all([
  import(pathToFileURL(join(generated, "FusionFlowLexer.js")).href),
  import(pathToFileURL(join(generated, "FusionFlowParser.js")).href),
]);

function parse(source) {
  const errors = [];
  const listener = {
    syntaxError(_recognizer, _offendingSymbol, line, column, message) {
      errors.push(line + ":" + column + " " + message);
    },
  };
  const lexer = new FusionFlowLexer(CharStream.fromString(source));
  lexer.removeErrorListeners();
  lexer.addErrorListener(listener);
  const parser = new FusionFlowParser(new CommonTokenStream(lexer));
  parser.removeErrorListeners();
  parser.addErrorListener(listener);
  parser.workflowFile();
  return errors;
}

assert.deepEqual(parse(example), [], "operator catalog example");
assert.notDeepEqual(
  parse(
    "workflow sample { step_executor(review) = if (true) { writer } else { human }; }",
  ),
  [],
  "must reject block-style if",
);
assert.notDeepEqual(
  parse("workflow sample { consumes_multi(step) = {source, report}; }"),
  [],
  "must reject the removed multi-set assertion shape",
);
assert.deepEqual(
  parse(
    "workflow sample { input_workflow_multi(flow) = [source]; consumes_multi(step) = [source, report]; produces_multi(step) = []; }",
  ),
  [],
  "multi operators return ordinary List terms",
);
assert.deepEqual(
  parse("workflow sample { custom(value, value, value) = true; }"),
  [],
  "externally registered operators keep checker-owned arity",
);
for (const source of [
  "concept Step; workflow sample {}",
  "op custom(Step) -> Bool; workflow sample {}",
  "workflow sample { const step:Step; }",
  "workflow sample { foreach_item(step, items) = File; }",
]) {
  assert.notDeepEqual(parse(source), [], "must reject removed local schema/variable syntax");
}
assert.deepEqual(
  parse(
    "workflow sample { step_executor(review) = if(!(max_attempts(review) != 2) AND (step_timeout(review) > 30 OR max_turns(agent) = 8), writer, human); }",
  ),
  [],
  "formula supports !, AND, OR, and comparisons",
);
for (const source of [
  "workflow sample { step_executor(review) = if(true = true IMPLIES false = false, writer, human); }",
  "workflow sample { step_executor(review) = if(true = true IFF false = false, writer, human); }",
  "workflow sample { step_executor(review) = if(not (true = true), writer, human); }",
  "workflow sample { step_executor(review) = if(~(true = true), writer, human); }",
]) {
  assert.notDeepEqual(parse(source), [], "must reject removed logical syntax");
}
for (const source of [
  "workflow sample { step_executor(review) = if(true = true, writer); }",
  "workflow sample { step_executor(review) = if(true = true, writer, human, fallback); }",
]) {
  assert.notDeepEqual(parse(source), [], "must enforce ternary if arity");
}

for (const operators of Object.values(operatorCategories)) {
  for (const [operator, arity] of Object.entries(operators)) {
    for (const wrongArity of [arity - 1, arity + 1]) {
      const args = Array.from({ length: wrongArity }, () => "value").join(", ");
      const source = "workflow sample { " + operator + "(" + args + ") = true; }";
      assert.deepEqual(
        parse(source),
        [],
        "checker-owned arity for " + operator + "/" + wrongArity,
      );
    }
  }
}

console.log("grammar runtime contract: ok");
