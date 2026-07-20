import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const loosePath = join(root, "grammar", "FusionFlow.g4");
const strictPath = join(root, "grammar", "FusionFlowStrict.g4");
const examplePath = join(root, "examples", "operator-catalog.workflow");
const looseGrammar = readFileSync(loosePath, "utf8");
const strictGrammar = readFileSync(strictPath, "utf8");
const example = readFileSync(examplePath, "utf8");

const operatorCategories = {
  workflowOwnerOperator: {
    input_workflow: 2,
    output_workflow: 2,
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
    produces: 2,
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
  surfaceOnlyOperator: {
    consumes_multi: 1,
  },
};

function ruleBody(grammar, name) {
  const match = grammar.match(new RegExp("\\b" + name + "\\s*:(.*?);", "s"));
  assert.ok(match, "missing " + name + " rule");
  return match[1];
}

for (const [category, operators] of Object.entries(operatorCategories)) {
  for (const grammar of [looseGrammar, strictGrammar]) {
    const body = ruleBody(grammar, category);
    for (const operator of Object.keys(operators)) {
      assert.match(body, new RegExp("['\\\"]" + operator + "['\\\"]"));
    }
  }

  for (const operator of Object.keys(operators)) {
    assert.match(example, new RegExp("\\b" + operator + "\\s*\\("));
  }
}

for (const grammar of [looseGrammar, strictGrammar]) {
  assert.match(
    grammar,
    /ifExpression\s*:\s*IF\s+LPAREN\s+formula\s+COMMA\s+term\s+COMMA\s+term\s+RPAREN\s*;/s,
  );
  assert.doesNotMatch(grammar, /\bELSE\b|\bbranch(?:Stmt|Arm)\b/);
}

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
const [{ FusionFlowStrictLexer }, { FusionFlowStrictParser }] =
  await Promise.all([
    import(pathToFileURL(join(generated, "FusionFlowStrictLexer.js")).href),
    import(pathToFileURL(join(generated, "FusionFlowStrictParser.js")).href),
  ]);

function parse(source, Lexer, Parser) {
  const errors = [];
  const listener = {
    syntaxError(_recognizer, _offendingSymbol, line, column, message) {
      errors.push(line + ":" + column + " " + message);
    },
  };
  const lexer = new Lexer(CharStream.fromString(source));
  lexer.removeErrorListeners();
  lexer.addErrorListener(listener);
  const parser = new Parser(new CommonTokenStream(lexer));
  parser.removeErrorListeners();
  parser.addErrorListener(listener);
  parser.workflowFile();
  return errors;
}

const parsers = [
  ["loose", FusionFlowLexer, FusionFlowParser],
  ["strict", FusionFlowStrictLexer, FusionFlowStrictParser],
];

for (const [name, Lexer, Parser] of parsers) {
  assert.deepEqual(parse(example, Lexer, Parser), [], name + " example");
  assert.notDeepEqual(
    parse(
      "workflow sample { step_executor(review) = if (true) { writer } else { human }; }",
      Lexer,
      Parser,
    ),
    [],
    name + " must reject block-style if",
  );
  assert.notDeepEqual(
    parse("workflow sample { consumes_multi(step) = true; }", Lexer, Parser),
    [],
    name + " must keep consumes_multi surface-only",
  );
  assert.deepEqual(
    parse("workflow sample { custom(value, value, value) = true; }", Lexer, Parser),
    [],
    name + " user operators keep flexible arity",
  );
  for (const source of [
    "workflow sample { step_executor(review) = if(true = true, writer); }",
    "workflow sample { step_executor(review) = if(true = true, writer, human, fallback); }",
  ]) {
    assert.notDeepEqual(
      parse(source, Lexer, Parser),
      [],
      name + " must enforce ternary if arity",
    );
  }
}

for (const operators of Object.values(operatorCategories).slice(0, -1)) {
  for (const [operator, arity] of Object.entries(operators)) {
    for (const wrongArity of [arity - 1, arity + 1]) {
      const args = Array.from({ length: wrongArity }, () => "value").join(", ");
      const source = "workflow sample { " + operator + "(" + args + ") = true; }";
      assert.deepEqual(
        parse(source, FusionFlowLexer, FusionFlowParser),
        [],
        "loose " + operator + "/" + wrongArity,
      );
      assert.notDeepEqual(
        parse(source, FusionFlowStrictLexer, FusionFlowStrictParser),
        [],
        "strict " + operator + "/" + wrongArity,
      );
    }
  }
}

console.log("grammar runtime contract: ok");
