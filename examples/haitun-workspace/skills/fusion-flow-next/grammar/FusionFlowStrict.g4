/*
 * Strict comparison grammar for FusionFlow.
 *
 * It shares the loose grammar's language surface, but enforces exact arity for
 * the 19 callable preset operators. User-declared operators remain flexible so
 * their declared signatures can be validated by the static checker.
 */
grammar FusionFlowStrict;

workflowFile
    : (declaration SEMICOLON)* workflowDecl+ EOF
    ;

workflowDecl
    : WORKFLOW workflowName LBRACE workflowItem* RBRACE
    ;

workflowName
    : identifier
    ;

workflowItem
    : declaration SEMICOLON
    | assertion SEMICOLON
    ;

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

opDecl
    : OP operatorName LPAREN conceptNameList? RPAREN (ARROW conceptName)?
    ;

conceptNameList
    : conceptName (COMMA conceptName)*
    ;

assertion
    : consumesMultiAssertion
    | term EQUALITY term
    ;

/* consumes_multi(Step) = {Artifact, ...}; surface syntax only, arity 1. */
consumesMultiAssertion
    : 'consumes_multi' LPAREN term RPAREN EQUALITY artifactSet
    ;

artifactSet
    : LBRACE (constantName (COMMA constantName)*)? RBRACE
    ;

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

term
    : LPAREN term RPAREN
    | ifExpression
    | workflowBuiltinApplication
    | userOperatorApplication
    | listLiteral
    | op=(PLUS | MINUS) term
    | <assoc=right> left=term op=CARET right=term
    | left=term op=(STAR | DIVIDE | MODULO) right=term
    | left=term op=(PLUS | MINUS) right=term
    | atomicTerm
    ;

/* A value-producing ternary expression; N-way branching is expressed by nesting. */
ifExpression
    : IF LPAREN formula COMMA term COMMA term RPAREN
    ;

workflowBuiltinApplication
    : workflowOwnerOperatorApplication
    | stepOwnerOperatorApplication
    | dataResourceOperatorApplication
    | agentOwnerOperatorApplication
    ;

workflowOwnerOperatorApplication
    : 'input_workflow' LPAREN term COMMA term RPAREN
    | 'output_workflow' LPAREN term COMMA term RPAREN
    | 'max_concurrency' LPAREN term RPAREN
    | 'workflow_timeout' LPAREN term RPAREN
    ;

stepOwnerOperatorApplication
    : 'step_name' LPAREN term RPAREN
    | 'step_instruction' LPAREN term RPAREN
    | 'step_executor' LPAREN term RPAREN
    | 'step_timeout' LPAREN term RPAREN
    | 'max_attempts' LPAREN term RPAREN
    ;

dataResourceOperatorApplication
    : 'consumes' LPAREN term COMMA term RPAREN
    | 'produces' LPAREN term COMMA term RPAREN
    | 'foreach_item' LPAREN term COMMA term RPAREN
    | 'resource_requirement' LPAREN term COMMA term RPAREN
    ;

agentOwnerOperatorApplication
    : 'agent_config' LPAREN term COMMA term COMMA term COMMA term RPAREN
    | 'allowed_tool' LPAREN term COMMA term RPAREN
    | 'max_output_tokens' LPAREN term RPAREN
    | 'temperature' LPAREN term RPAREN
    | 'reasoning_effort' LPAREN term RPAREN
    | 'max_turns' LPAREN term RPAREN
    ;

userOperatorApplication
    : LOWID LPAREN termList? RPAREN
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

identifier
    : LOWID
    ;

conceptName
    : UPID
    ;

/* consumes_multi is excluded because it is valid only in consumesMultiAssertion. */
operatorName
    : LOWID
    | callableWorkflowBuiltinOperator
    ;

/* Complete 20-name preset catalog, including the one surface-only operator. */
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
 * Workflow owner: input_workflow/2, output_workflow/2, max_concurrency/1,
 * workflow_timeout/1.
 */
workflowOwnerOperator
    : 'input_workflow'
    | 'output_workflow'
    | 'max_concurrency'
    | 'workflow_timeout'
    ;

/* Step owner: step_name/1, step_instruction/1, step_executor/1,
 * step_timeout/1, max_attempts/1. */
stepOwnerOperator
    : 'step_name'
    | 'step_instruction'
    | 'step_executor'
    | 'step_timeout'
    | 'max_attempts'
    ;

/* Data/resource: consumes/2, produces/2, foreach_item/2,
 * resource_requirement/2. */
dataResourceOperator
    : 'consumes'
    | 'produces'
    | 'foreach_item'
    | 'resource_requirement'
    ;

/* Agent owner: agent_config/4, allowed_tool/2, max_output_tokens/1,
 * temperature/1, reasoning_effort/1, max_turns/1. */
agentOwnerOperator
    : 'agent_config'
    | 'allowed_tool'
    | 'max_output_tokens'
    | 'temperature'
    | 'reasoning_effort'
    | 'max_turns'
    ;

surfaceOnlyOperator
    : 'consumes_multi'
    ;

variableName
    : UPID
    ;

constantName
    : NUMBER
    | QUOTEDCONSTANTID
    | LOWID
    ;

booleanLiteral
    : TRUE
    | FALSE
    ;

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
