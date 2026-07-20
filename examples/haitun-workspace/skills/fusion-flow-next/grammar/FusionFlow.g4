/*
 * FusionFlow surface-syntax contract.
 *
 * The parser owns tokens, delimiters, declarations, assertions, formulas,
 * terms, the three-argument shape of if(...), collection placement, and the
 * names and owner categories of the preset operators.
 *
 * The static checker owns declaration/reference resolution, concept
 * compatibility, ordinary preset/user operator contracts, call arity and
 * types, value constraints, workflow legality, and exact backend-lowering support.
 * Lowering/runtime own execution order, dependencies, branch evaluation,
 * retries/timeouts, and consumes_multi expansion. Callable preset and user
 * operators therefore share the same flexible call syntax here; there is
 * intentionally no second semantic grammar to keep in sync.
 */
grammar FusionFlow;

/* A file has optional global declarations followed by one or more workflows. */
workflowFile
    : (declaration SEMICOLON)* workflowDecl+ EOF
    ;

workflowDecl
    : WORKFLOW workflowName LBRACE workflowItem* RBRACE
    ;

workflowName
    : identifier
    ;

/* Every declaration and assertion inside a workflow ends with a semicolon. */
workflowItem
    : declaration SEMICOLON
    | assertion SEMICOLON
    ;

/* Concepts, typed constants, and user-defined operator signatures. */
declaration
    : conceptDecl
    | constDecl
    | opDecl
    ;

conceptDecl
    : CONCEPT conceptName (COLON conceptName)?
    ;

constDecl
    : CONST constantName COLON conceptNameList
    ;

/* Signature existence, inheritance, arity, and type validity are checker-owned. */
opDecl
    : OP operatorName LPAREN conceptNameList? RPAREN (ARROW conceptName)?
    ;

conceptNameList
    : conceptName (COMMA conceptName)*
    ;

/* Equality is a relation, not imperative assignment; both '=' and '==' parse. */
assertion
    : consumesMultiAssertion
    | term EQUALITY term
    ;

/*
 * Dedicated surface syntax: consumes_multi(Step) = {Artifact, ...}.
 * It is not a generic term call. The set may be empty syntactically and may
 * contain only constant names; cardinality and dependency semantics are
 * checker/runtime concerns.
 */
consumesMultiAssertion
    : 'consumes_multi' LPAREN term RPAREN EQUALITY artifactSet
    ;

artifactSet
    : LBRACE (constantName (COMMA constantName)*)? RBRACE
    ;

/*
 * Conditions bottom out at term comparisons; a bare term is not a formula.
 * Logical precedence, high to low: NOT, AND, OR, right-associative IMPLIES,
 * then IFF. Parentheses override it.
 */
formula
    : LPAREN formula RPAREN
    | NOT formula
    | left=formula AND right=formula
    | left=formula OR right=formula
    | <assoc=right> left=formula IMPLIES right=formula
    | left=formula IFF right=formula
    | comparison
    ;

comparison
    : term comparisonOp term
    ;

comparisonOp
    : EQUALITY
    | NOT_EQUALS
    | LT
    | LTE
    | GT
    | GTE
    ;

/*
 * Value terms include calls, lists, literals, arithmetic, and if expressions.
 * Arithmetic precedence, high to low: unary +/-; right-associative ^; * / %;
 * then +/-. Lists are terms, but {...} sets are consumes_multi-only.
 * Numeric/operator type legality remains checker-owned.
 */
term
    : LPAREN term RPAREN
    | ifExpression
    | operatorName LPAREN termList? RPAREN
    | listLiteral
    | op=(PLUS | MINUS) term
    | <assoc=right> left=term op=CARET right=term
    | left=term op=(STAR | DIVIDE | MODULO) right=term
    | left=term op=(PLUS | MINUS) right=term
    | atomicTerm
    ;

/*
 * Value-producing if(condition formula, then term, else term), always arity 3.
 * N-way choice uses nested if expressions. Branch types, dependency collection,
 * and eager/lazy evaluation are checker/runtime concerns. if is surface syntax,
 * not one of the 20 preset operators and not a block or Step.
 */
ifExpression
    : IF LPAREN formula COMMA term COMMA term RPAREN
    ;

termList
    : term (COMMA term)*
    ;

listLiteral
    : LBRACK termList? RBRACK
    ;

atomicTerm
    : variableName
    | constantName
    | booleanLiteral
    ;

/* Lowercase names identify workflows, constants, and user-defined operators. */
identifier
    : LOWID
    ;

conceptName
    : UPID
    ;

/* consumes_multi is reserved for consumesMultiAssertion and cannot be called here. */
operatorName
    : LOWID
    | callableWorkflowBuiltinOperator
    ;

/*
 * Complete catalog: 4 workflow + 5 step + 4 data/resource + 6 agent
 * operators, plus 1 surface-only operator = 20. Owner categories are disjoint;
 * cross-cutting labels such as dataflow, control, and configuration stay in
 * comments rather than duplicating names across parser rules.
 */
workflowBuiltinOperator
    : callableWorkflowBuiltinOperator
    | surfaceOnlyOperator
    ;

callableWorkflowBuiltinOperator
    : workflowOwnerOperator
    | stepOwnerOperator
    | dataResourceOperator
    | agentOwnerOperator
    ;

/*
 * Workflow owner (external I/O and workflow-level control/configuration):
 *   input_workflow(Workflow, Artifact) -> Bool       [arity 2]
 *   output_workflow(Workflow, Artifact) -> Bool      [arity 2]
 *   max_concurrency(Workflow) -> Integer             [arity 1]
 *   workflow_timeout(Workflow) -> Integer            [arity 1]
 */
workflowOwnerOperator
    : 'input_workflow'
    | 'output_workflow'
    | 'max_concurrency'
    | 'workflow_timeout'
    ;

/*
 * Step owner (identity, execution binding, timeout, and retry configuration):
 *   step_name(Step) -> StepName                      [arity 1]
 *   step_instruction(Step) -> Instruction            [arity 1]
 *   step_executor(Step) -> Executor                  [arity 1]
 *   step_timeout(Step) -> Integer                    [arity 1]
 *   max_attempts(Step) -> Integer                    [arity 1]
 */
stepOwnerOperator
    : 'step_name'
    | 'step_instruction'
    | 'step_executor'
    | 'step_timeout'
    | 'max_attempts'
    ;

/*
 * Data, loop, and resource owner:
 *   consumes(Step, Artifact) -> Bool                  [arity 2]
 *   produces(Step, Artifact) -> Bool                  [arity 2]
 *   foreach_item(Step, List) -> Artifact              [arity 2]
 *   resource_requirement(Step, Resource) -> Integer   [arity 2]
 */
dataResourceOperator
    : 'consumes'
    | 'produces'
    | 'foreach_item'
    | 'resource_requirement'
    ;

/*
 * Agent owner (model/runtime configuration and execution limits):
 *   agent_config(Agent, Model, Engine, ApiBase) -> Bool [arity 4]
 *   allowed_tool(Agent, Tool) -> Bool                   [arity 2]
 *   max_output_tokens(Agent) -> Integer                 [arity 1]
 *   temperature(Agent) -> ComplexNumber                 [arity 1]
 *   reasoning_effort(Agent) -> ReasoningEffort          [arity 1]
 *   max_turns(Agent) -> Integer                         [arity 1]
 */
agentOwnerOperator
    : 'agent_config'
    | 'allowed_tool'
    | 'max_output_tokens'
    | 'temperature'
    | 'reasoning_effort'
    | 'max_turns'
    ;

/* consumes_multi(Step) = ArtifactSet [surface arity 1]. */
surfaceOnlyOperator
    : 'consumes_multi'
    ;

/* Uppercase term names are variables; uppercase declaration names are concepts. */
variableName
    : UPID
    ;

/* Constants are numbers, restricted quoted IDs, or lowercase identifiers. */
constantName
    : NUMBER
    | QUOTEDCONSTANTID
    | LOWID
    ;

booleanLiteral
    : TRUE
    | FALSE
    ;

/* Keywords and symbolic aliases are case-sensitive exactly as listed below. */
WORKFLOW : 'workflow';
IF : 'if';
CONCEPT : 'concept';
CONST : 'const';
OP : 'op';
AND : 'AND' | 'and' | '&';
OR : 'OR' | 'or' | '|';
NOT : 'NOT' | 'not' | '~';
IMPLIES : 'IMPLIES' | 'implies' | '>>';
IFF : 'IFF' | 'iff' | '<==>';
TRUE : 'True' | 'true' | 'TRUE';
FALSE : 'False' | 'false' | 'FALSE';
EQUALITY : '==' | '=';
NOT_EQUALS : '!=';
LTE : '<=';
GTE : '>=';
LT : '<';
GT : '>';
PLUS : '+';
MINUS : '-';
STAR : '*';
DIVIDE : '/';
MODULO : '%';
CARET : '^';
ARROW : '->';

NUMBER
    : DIGITS '.' DIGITS
    | DIGITS
    ;

fragment DIGIT : [0-9];
fragment DIGITS : DIGIT+;
fragment UPPERID : [A-Z][A-Za-z0-9_]*;
fragment LOWERID : [a-z][A-Za-z0-9_]*;

UPID : UPPERID;
LOWID : LOWERID;
/* Restricted ID, not a general string: no whitespace or escape sequences. */
QUOTEDCONSTANTID : '"' [A-Za-z0-9.!#$%?@_{|}~`]* '"';
COLON : ':';
COMMA : ',';
SEMICOLON : ';';
LPAREN : '(';
RPAREN : ')';
LBRACE : '{';
RBRACE : '}';
LBRACK : '[';
RBRACK : ']';
WS : [ \t\r\n]+ -> skip;
LINE_COMMENT : '--' ~[\r\n]* -> skip;
BLOCK_COMMENT : '/*' .*? '*/' -> skip;
