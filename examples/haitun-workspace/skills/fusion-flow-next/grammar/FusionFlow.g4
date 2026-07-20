/*
 * This grammar owns syntax only. Operator meaning, ownership, and backend
 * support belong to the checker; only the documented bootstrap surface is here.
 * The future Core IR visitor normalizes == to = while lowering the parse tree.
 */
grammar FusionFlow;

workflowFile
    : workflowDeclaration EOF
    ;

workflowDeclaration
    : WORKFLOW IDENTIFIER LBRACE assertion* RBRACE
    ;

assertion
    : operatorCall equalityOperator value SEMICOLON
    ;

operatorCall
    : IDENTIFIER LPAREN argumentList? RPAREN
    ;

argumentList
    : value (COMMA value)*
    ;

equalityOperator
    : EQUAL
    | DOUBLE_EQUAL
    ;

value
    : IDENTIFIER
    | booleanLiteral
    | listLiteral
    ;

booleanLiteral
    : TRUE
    | FALSE
    ;

listLiteral
    : LBRACKET (value (COMMA value)*)? RBRACKET
    ;

WORKFLOW: 'workflow';
TRUE: 'True';
FALSE: 'False';
DOUBLE_EQUAL: '==';
EQUAL: '=';
LBRACE: '{';
RBRACE: '}';
LPAREN: '(';
RPAREN: ')';
LBRACKET: '[';
RBRACKET: ']';
COMMA: ',';
SEMICOLON: ';';
IDENTIFIER: [a-zA-Z_] [a-zA-Z0-9_]*;
WS: [ \t\r\n]+ -> skip;
