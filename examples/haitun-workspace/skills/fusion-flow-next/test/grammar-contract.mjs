import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const grammar = readFileSync(join(root, "grammar", "FusionFlow.g4"), "utf8");

const presetOperators = [
  ...grammar.matchAll(/^\s*(?::|\|)\s*'([a-z][a-z0-9_]*)'\s*$/gm),
].map((match) => match[1]);
const signatures = [
  ...grammar.matchAll(
    /^\s*\*\s+([a-z][a-z0-9_]*)\(([^)]*)\)\s*->\s*[A-Z][A-Za-z0-9_]*\s+\[arity\s+(\d+)\]\s*$/gm,
  ),
];

assert.deepEqual(
  signatures.map((match) => match[1]).sort(),
  [...new Set(presetOperators)].sort(),
  "every preset operator must document parameter types, return type, and arity",
);

for (const [, operator, parameters, arity] of signatures) {
  const parameterTypes = parameters.trim()
    ? parameters.split(",").map((type) => type.trim())
    : [];
  assert.ok(
    parameterTypes.every((type) => /^[A-Z][A-Za-z0-9_]*$/.test(type)),
    operator + " must document every parameter type",
  );
  assert.equal(
    parameterTypes.length,
    Number(arity),
    operator + " documented parameter count must match its arity",
  );
}

console.log("grammar operator documentation contract: ok");
