
import * as antlr from "antlr4ng";
import { Token } from "antlr4ng";

import { FusionFlowVisitor } from "./FusionFlowVisitor.js";

// for running tests with parameters, TODO: discuss strategy for typed parameters in CI
// eslint-disable-next-line no-unused-vars
type int = number;


export class FusionFlowParser extends antlr.Parser {
    public static readonly T__0 = 1;
    public static readonly T__1 = 2;
    public static readonly T__2 = 3;
    public static readonly T__3 = 4;
    public static readonly T__4 = 5;
    public static readonly T__5 = 6;
    public static readonly T__6 = 7;
    public static readonly T__7 = 8;
    public static readonly T__8 = 9;
    public static readonly T__9 = 10;
    public static readonly T__10 = 11;
    public static readonly T__11 = 12;
    public static readonly T__12 = 13;
    public static readonly T__13 = 14;
    public static readonly T__14 = 15;
    public static readonly T__15 = 16;
    public static readonly T__16 = 17;
    public static readonly T__17 = 18;
    public static readonly T__18 = 19;
    public static readonly T__19 = 20;
    public static readonly T__20 = 21;
    public static readonly T__21 = 22;
    public static readonly T__22 = 23;
    public static readonly WORKFLOW = 24;
    public static readonly IF = 25;
    public static readonly CONST = 26;
    public static readonly AND = 27;
    public static readonly OR = 28;
    public static readonly NOT = 29;
    public static readonly TRUE = 30;
    public static readonly FALSE = 31;
    public static readonly ASSERT_EQ = 32;
    public static readonly NUMERIC_EQ = 33;
    public static readonly NOT_EQUALS = 34;
    public static readonly LTE = 35;
    public static readonly GTE = 36;
    public static readonly LT = 37;
    public static readonly GT = 38;
    public static readonly PLUS = 39;
    public static readonly MINUS = 40;
    public static readonly STAR = 41;
    public static readonly DIVIDE = 42;
    public static readonly MODULO = 43;
    public static readonly CARET = 44;
    public static readonly NUMBER = 45;
    public static readonly UPID = 46;
    public static readonly LOWID = 47;
    public static readonly QUOTEDCONSTANTID = 48;
    public static readonly COLON = 49;
    public static readonly COMMA = 50;
    public static readonly SEMICOLON = 51;
    public static readonly LPAREN = 52;
    public static readonly RPAREN = 53;
    public static readonly LBRACE = 54;
    public static readonly RBRACE = 55;
    public static readonly LBRACK = 56;
    public static readonly RBRACK = 57;
    public static readonly WS = 58;
    public static readonly LINE_COMMENT = 59;
    public static readonly BLOCK_COMMENT = 60;
    public static readonly RULE_workflowFile = 0;
    public static readonly RULE_workflowDecl = 1;
    public static readonly RULE_workflowName = 2;
    public static readonly RULE_workflowItem = 3;
    public static readonly RULE_constDecl = 4;
    public static readonly RULE_conceptNameList = 5;
    public static readonly RULE_assertion = 6;
    public static readonly RULE_formula = 7;
    public static readonly RULE_comparison = 8;
    public static readonly RULE_comparisonOp = 9;
    public static readonly RULE_term = 10;
    public static readonly RULE_ifExpression = 11;
    public static readonly RULE_termList = 12;
    public static readonly RULE_listLiteral = 13;
    public static readonly RULE_atomicTerm = 14;
    public static readonly RULE_identifier = 15;
    public static readonly RULE_conceptName = 16;
    public static readonly RULE_operatorName = 17;
    public static readonly RULE_workflowBuiltinOperator = 18;
    public static readonly RULE_workflowOwnerOperator = 19;
    public static readonly RULE_stepOwnerOperator = 20;
    public static readonly RULE_dataResourceOperator = 21;
    public static readonly RULE_agentOwnerOperator = 22;
    public static readonly RULE_constantName = 23;
    public static readonly RULE_booleanLiteral = 24;

    public static readonly literalNames = [
        null, "'input_workflow'", "'input_workflow_multi'", "'output_workflow'", 
        "'output_workflow_multi'", "'max_concurrency'", "'workflow_timeout'", 
        "'step_name'", "'step_instruction'", "'step_executor'", "'step_timeout'", 
        "'max_attempts'", "'consumes'", "'consumes_multi'", "'produces'", 
        "'produces_multi'", "'foreach_item'", "'resource_requirement'", 
        "'agent_config'", "'allowed_tool'", "'max_output_tokens'", "'temperature'", 
        "'reasoning_effort'", "'max_turns'", "'workflow'", "'if'", "'const'", 
        null, null, "'!'", null, null, "'=='", "'='", "'!='", "'<='", "'>='", 
        "'<'", "'>'", "'+'", "'-'", "'*'", "'/'", "'%'", "'^'", null, null, 
        null, null, "':'", "','", "';'", "'('", "')'", "'{'", "'}'", "'['", 
        "']'"
    ];

    public static readonly symbolicNames = [
        null, null, null, null, null, null, null, null, null, null, null, 
        null, null, null, null, null, null, null, null, null, null, null, 
        null, null, "WORKFLOW", "IF", "CONST", "AND", "OR", "NOT", "TRUE", 
        "FALSE", "ASSERT_EQ", "NUMERIC_EQ", "NOT_EQUALS", "LTE", "GTE", 
        "LT", "GT", "PLUS", "MINUS", "STAR", "DIVIDE", "MODULO", "CARET", 
        "NUMBER", "UPID", "LOWID", "QUOTEDCONSTANTID", "COLON", "COMMA", 
        "SEMICOLON", "LPAREN", "RPAREN", "LBRACE", "RBRACE", "LBRACK", "RBRACK", 
        "WS", "LINE_COMMENT", "BLOCK_COMMENT"
    ];
    public static readonly ruleNames = [
        "workflowFile", "workflowDecl", "workflowName", "workflowItem", 
        "constDecl", "conceptNameList", "assertion", "formula", "comparison", 
        "comparisonOp", "term", "ifExpression", "termList", "listLiteral", 
        "atomicTerm", "identifier", "conceptName", "operatorName", "workflowBuiltinOperator", 
        "workflowOwnerOperator", "stepOwnerOperator", "dataResourceOperator", 
        "agentOwnerOperator", "constantName", "booleanLiteral",
    ];

    public get grammarFileName(): string { return "FusionFlow.g4"; }
    public get literalNames(): (string | null)[] { return FusionFlowParser.literalNames; }
    public get symbolicNames(): (string | null)[] { return FusionFlowParser.symbolicNames; }
    public get ruleNames(): string[] { return FusionFlowParser.ruleNames; }
    public get serializedATN(): number[] { return FusionFlowParser._serializedATN; }

    protected createFailedPredicateException(predicate?: string, message?: string): antlr.FailedPredicateException {
        return new antlr.FailedPredicateException(this, predicate, message);
    }

    public constructor(input: antlr.TokenStream) {
        super(input);
        this.interpreter = new antlr.ParserATNSimulator(this, FusionFlowParser._ATN, FusionFlowParser.decisionsToDFA, new antlr.PredictionContextCache());
    }
    public workflowFile(): WorkflowFileContext {
        let localContext = new WorkflowFileContext(this.context, this.state);
        this.enterRule(localContext, 0, FusionFlowParser.RULE_workflowFile);
        let _la: number;
        try {
            this.enterOuterAlt(localContext, 1);
            {
            this.state = 55;
            this.errorHandler.sync(this);
            _la = this.tokenStream.LA(1);
            while (_la === 26) {
                {
                {
                this.state = 50;
                this.constDecl();
                this.state = 51;
                this.match(FusionFlowParser.SEMICOLON);
                }
                }
                this.state = 57;
                this.errorHandler.sync(this);
                _la = this.tokenStream.LA(1);
            }
            this.state = 59;
            this.errorHandler.sync(this);
            _la = this.tokenStream.LA(1);
            do {
                {
                {
                this.state = 58;
                this.workflowDecl();
                }
                }
                this.state = 61;
                this.errorHandler.sync(this);
                _la = this.tokenStream.LA(1);
            } while (_la === 24);
            this.state = 63;
            this.match(FusionFlowParser.EOF);
            }
        }
        catch (re) {
            if (re instanceof antlr.RecognitionException) {
                this.errorHandler.reportError(this, re);
                this.errorHandler.recover(this, re);
            } else {
                throw re;
            }
        }
        finally {
            this.exitRule();
        }
        return localContext;
    }
    public workflowDecl(): WorkflowDeclContext {
        let localContext = new WorkflowDeclContext(this.context, this.state);
        this.enterRule(localContext, 2, FusionFlowParser.RULE_workflowDecl);
        let _la: number;
        try {
            this.enterOuterAlt(localContext, 1);
            {
            this.state = 65;
            this.match(FusionFlowParser.WORKFLOW);
            this.state = 66;
            this.workflowName();
            this.state = 67;
            this.match(FusionFlowParser.LBRACE);
            this.state = 71;
            this.errorHandler.sync(this);
            _la = this.tokenStream.LA(1);
            while ((((_la) & ~0x1F) === 0 && ((1 << _la) & 3271557118) !== 0) || ((((_la - 39)) & ~0x1F) === 0 && ((1 << (_la - 39)) & 140099) !== 0)) {
                {
                {
                this.state = 68;
                this.workflowItem();
                }
                }
                this.state = 73;
                this.errorHandler.sync(this);
                _la = this.tokenStream.LA(1);
            }
            this.state = 74;
            this.match(FusionFlowParser.RBRACE);
            }
        }
        catch (re) {
            if (re instanceof antlr.RecognitionException) {
                this.errorHandler.reportError(this, re);
                this.errorHandler.recover(this, re);
            } else {
                throw re;
            }
        }
        finally {
            this.exitRule();
        }
        return localContext;
    }
    public workflowName(): WorkflowNameContext {
        let localContext = new WorkflowNameContext(this.context, this.state);
        this.enterRule(localContext, 4, FusionFlowParser.RULE_workflowName);
        try {
            this.enterOuterAlt(localContext, 1);
            {
            this.state = 76;
            this.identifier();
            }
        }
        catch (re) {
            if (re instanceof antlr.RecognitionException) {
                this.errorHandler.reportError(this, re);
                this.errorHandler.recover(this, re);
            } else {
                throw re;
            }
        }
        finally {
            this.exitRule();
        }
        return localContext;
    }
    public workflowItem(): WorkflowItemContext {
        let localContext = new WorkflowItemContext(this.context, this.state);
        this.enterRule(localContext, 6, FusionFlowParser.RULE_workflowItem);
        try {
            this.enterOuterAlt(localContext, 1);
            {
            this.state = 78;
            this.assertion();
            this.state = 79;
            this.match(FusionFlowParser.SEMICOLON);
            }
        }
        catch (re) {
            if (re instanceof antlr.RecognitionException) {
                this.errorHandler.reportError(this, re);
                this.errorHandler.recover(this, re);
            } else {
                throw re;
            }
        }
        finally {
            this.exitRule();
        }
        return localContext;
    }
    public constDecl(): ConstDeclContext {
        let localContext = new ConstDeclContext(this.context, this.state);
        this.enterRule(localContext, 8, FusionFlowParser.RULE_constDecl);
        try {
            this.enterOuterAlt(localContext, 1);
            {
            this.state = 81;
            this.match(FusionFlowParser.CONST);
            this.state = 82;
            this.constantName();
            this.state = 83;
            this.match(FusionFlowParser.COLON);
            this.state = 84;
            this.conceptNameList();
            }
        }
        catch (re) {
            if (re instanceof antlr.RecognitionException) {
                this.errorHandler.reportError(this, re);
                this.errorHandler.recover(this, re);
            } else {
                throw re;
            }
        }
        finally {
            this.exitRule();
        }
        return localContext;
    }
    public conceptNameList(): ConceptNameListContext {
        let localContext = new ConceptNameListContext(this.context, this.state);
        this.enterRule(localContext, 10, FusionFlowParser.RULE_conceptNameList);
        let _la: number;
        try {
            this.enterOuterAlt(localContext, 1);
            {
            this.state = 86;
            this.conceptName();
            this.state = 91;
            this.errorHandler.sync(this);
            _la = this.tokenStream.LA(1);
            while (_la === 50) {
                {
                {
                this.state = 87;
                this.match(FusionFlowParser.COMMA);
                this.state = 88;
                this.conceptName();
                }
                }
                this.state = 93;
                this.errorHandler.sync(this);
                _la = this.tokenStream.LA(1);
            }
            }
        }
        catch (re) {
            if (re instanceof antlr.RecognitionException) {
                this.errorHandler.reportError(this, re);
                this.errorHandler.recover(this, re);
            } else {
                throw re;
            }
        }
        finally {
            this.exitRule();
        }
        return localContext;
    }
    public assertion(): AssertionContext {
        let localContext = new AssertionContext(this.context, this.state);
        this.enterRule(localContext, 12, FusionFlowParser.RULE_assertion);
        try {
            this.enterOuterAlt(localContext, 1);
            {
            this.state = 94;
            this.term(0);
            this.state = 95;
            this.match(FusionFlowParser.ASSERT_EQ);
            this.state = 96;
            this.term(0);
            }
        }
        catch (re) {
            if (re instanceof antlr.RecognitionException) {
                this.errorHandler.reportError(this, re);
                this.errorHandler.recover(this, re);
            } else {
                throw re;
            }
        }
        finally {
            this.exitRule();
        }
        return localContext;
    }

    public formula(): FormulaContext;
    public formula(_p: number): FormulaContext;
    public formula(_p?: number): FormulaContext {
        if (_p === undefined) {
            _p = 0;
        }

        let parentContext = this.context;
        let parentState = this.state;
        let localContext = new FormulaContext(this.context, parentState);
        let previousContext = localContext;
        let _startState = 14;
        this.enterRecursionRule(localContext, 14, FusionFlowParser.RULE_formula, _p);
        try {
            let alternative: number;
            this.enterOuterAlt(localContext, 1);
            {
            this.state = 106;
            this.errorHandler.sync(this);
            switch (this.interpreter.adaptivePredict(this.tokenStream, 4, this.context) ) {
            case 1:
                {
                this.state = 99;
                this.match(FusionFlowParser.LPAREN);
                this.state = 100;
                this.formula(0);
                this.state = 101;
                this.match(FusionFlowParser.RPAREN);
                }
                break;
            case 2:
                {
                this.state = 103;
                this.match(FusionFlowParser.NOT);
                this.state = 104;
                this.formula(4);
                }
                break;
            case 3:
                {
                this.state = 105;
                this.comparison();
                }
                break;
            }
            this.context!.stop = this.tokenStream.LT(-1);
            this.state = 116;
            this.errorHandler.sync(this);
            alternative = this.interpreter.adaptivePredict(this.tokenStream, 6, this.context);
            while (alternative !== 2 && alternative !== antlr.ATN.INVALID_ALT_NUMBER) {
                if (alternative === 1) {
                    if (this.parseListeners != null) {
                        this.triggerExitRuleEvent();
                    }
                    previousContext = localContext;
                    {
                    this.state = 114;
                    this.errorHandler.sync(this);
                    switch (this.interpreter.adaptivePredict(this.tokenStream, 5, this.context) ) {
                    case 1:
                        {
                        localContext = new FormulaContext(parentContext, parentState);
                        localContext._left = previousContext;
                        this.pushNewRecursionContext(localContext, _startState, FusionFlowParser.RULE_formula);
                        this.state = 108;
                        if (!(this.precpred(this.context, 3))) {
                            throw this.createFailedPredicateException("this.precpred(this.context, 3)");
                        }
                        this.state = 109;
                        this.match(FusionFlowParser.AND);
                        this.state = 110;
                        localContext._right = this.formula(4);
                        }
                        break;
                    case 2:
                        {
                        localContext = new FormulaContext(parentContext, parentState);
                        localContext._left = previousContext;
                        this.pushNewRecursionContext(localContext, _startState, FusionFlowParser.RULE_formula);
                        this.state = 111;
                        if (!(this.precpred(this.context, 2))) {
                            throw this.createFailedPredicateException("this.precpred(this.context, 2)");
                        }
                        this.state = 112;
                        this.match(FusionFlowParser.OR);
                        this.state = 113;
                        localContext._right = this.formula(3);
                        }
                        break;
                    }
                    }
                }
                this.state = 118;
                this.errorHandler.sync(this);
                alternative = this.interpreter.adaptivePredict(this.tokenStream, 6, this.context);
            }
            }
        }
        catch (re) {
            if (re instanceof antlr.RecognitionException) {
                this.errorHandler.reportError(this, re);
                this.errorHandler.recover(this, re);
            } else {
                throw re;
            }
        }
        finally {
            this.unrollRecursionContexts(parentContext);
        }
        return localContext;
    }
    public comparison(): ComparisonContext {
        let localContext = new ComparisonContext(this.context, this.state);
        this.enterRule(localContext, 16, FusionFlowParser.RULE_comparison);
        try {
            this.enterOuterAlt(localContext, 1);
            {
            this.state = 119;
            this.term(0);
            this.state = 120;
            this.comparisonOp();
            this.state = 121;
            this.term(0);
            }
        }
        catch (re) {
            if (re instanceof antlr.RecognitionException) {
                this.errorHandler.reportError(this, re);
                this.errorHandler.recover(this, re);
            } else {
                throw re;
            }
        }
        finally {
            this.exitRule();
        }
        return localContext;
    }
    public comparisonOp(): ComparisonOpContext {
        let localContext = new ComparisonOpContext(this.context, this.state);
        this.enterRule(localContext, 18, FusionFlowParser.RULE_comparisonOp);
        let _la: number;
        try {
            this.enterOuterAlt(localContext, 1);
            {
            this.state = 123;
            _la = this.tokenStream.LA(1);
            if(!(((((_la - 33)) & ~0x1F) === 0 && ((1 << (_la - 33)) & 63) !== 0))) {
            this.errorHandler.recoverInline(this);
            }
            else {
                this.errorHandler.reportMatch(this);
                this.consume();
            }
            }
        }
        catch (re) {
            if (re instanceof antlr.RecognitionException) {
                this.errorHandler.reportError(this, re);
                this.errorHandler.recover(this, re);
            } else {
                throw re;
            }
        }
        finally {
            this.exitRule();
        }
        return localContext;
    }

    public term(): TermContext;
    public term(_p: number): TermContext;
    public term(_p?: number): TermContext {
        if (_p === undefined) {
            _p = 0;
        }

        let parentContext = this.context;
        let parentState = this.state;
        let localContext = new TermContext(this.context, parentState);
        let previousContext = localContext;
        let _startState = 20;
        this.enterRecursionRule(localContext, 20, FusionFlowParser.RULE_term, _p);
        let _la: number;
        try {
            let alternative: number;
            this.enterOuterAlt(localContext, 1);
            {
            this.state = 142;
            this.errorHandler.sync(this);
            switch (this.interpreter.adaptivePredict(this.tokenStream, 8, this.context) ) {
            case 1:
                {
                this.state = 126;
                this.match(FusionFlowParser.LPAREN);
                this.state = 127;
                this.term(0);
                this.state = 128;
                this.match(FusionFlowParser.RPAREN);
                }
                break;
            case 2:
                {
                this.state = 130;
                this.ifExpression();
                }
                break;
            case 3:
                {
                this.state = 131;
                this.operatorName();
                this.state = 132;
                this.match(FusionFlowParser.LPAREN);
                this.state = 134;
                this.errorHandler.sync(this);
                _la = this.tokenStream.LA(1);
                if ((((_la) & ~0x1F) === 0 && ((1 << _la) & 3271557118) !== 0) || ((((_la - 39)) & ~0x1F) === 0 && ((1 << (_la - 39)) & 140099) !== 0)) {
                    {
                    this.state = 133;
                    this.termList();
                    }
                }

                this.state = 136;
                this.match(FusionFlowParser.RPAREN);
                }
                break;
            case 4:
                {
                this.state = 138;
                this.listLiteral();
                }
                break;
            case 5:
                {
                this.state = 139;
                localContext._op = this.tokenStream.LT(1);
                _la = this.tokenStream.LA(1);
                if(!(_la === 39 || _la === 40)) {
                    localContext._op = this.errorHandler.recoverInline(this);
                }
                else {
                    this.errorHandler.reportMatch(this);
                    this.consume();
                }
                this.state = 140;
                this.term(5);
                }
                break;
            case 6:
                {
                this.state = 141;
                this.atomicTerm();
                }
                break;
            }
            this.context!.stop = this.tokenStream.LT(-1);
            this.state = 155;
            this.errorHandler.sync(this);
            alternative = this.interpreter.adaptivePredict(this.tokenStream, 10, this.context);
            while (alternative !== 2 && alternative !== antlr.ATN.INVALID_ALT_NUMBER) {
                if (alternative === 1) {
                    if (this.parseListeners != null) {
                        this.triggerExitRuleEvent();
                    }
                    previousContext = localContext;
                    {
                    this.state = 153;
                    this.errorHandler.sync(this);
                    switch (this.interpreter.adaptivePredict(this.tokenStream, 9, this.context) ) {
                    case 1:
                        {
                        localContext = new TermContext(parentContext, parentState);
                        localContext._left = previousContext;
                        this.pushNewRecursionContext(localContext, _startState, FusionFlowParser.RULE_term);
                        this.state = 144;
                        if (!(this.precpred(this.context, 4))) {
                            throw this.createFailedPredicateException("this.precpred(this.context, 4)");
                        }
                        this.state = 145;
                        localContext._op = this.match(FusionFlowParser.CARET);
                        this.state = 146;
                        localContext._right = this.term(4);
                        }
                        break;
                    case 2:
                        {
                        localContext = new TermContext(parentContext, parentState);
                        localContext._left = previousContext;
                        this.pushNewRecursionContext(localContext, _startState, FusionFlowParser.RULE_term);
                        this.state = 147;
                        if (!(this.precpred(this.context, 3))) {
                            throw this.createFailedPredicateException("this.precpred(this.context, 3)");
                        }
                        this.state = 148;
                        localContext._op = this.tokenStream.LT(1);
                        _la = this.tokenStream.LA(1);
                        if(!(((((_la - 41)) & ~0x1F) === 0 && ((1 << (_la - 41)) & 7) !== 0))) {
                            localContext._op = this.errorHandler.recoverInline(this);
                        }
                        else {
                            this.errorHandler.reportMatch(this);
                            this.consume();
                        }
                        this.state = 149;
                        localContext._right = this.term(4);
                        }
                        break;
                    case 3:
                        {
                        localContext = new TermContext(parentContext, parentState);
                        localContext._left = previousContext;
                        this.pushNewRecursionContext(localContext, _startState, FusionFlowParser.RULE_term);
                        this.state = 150;
                        if (!(this.precpred(this.context, 2))) {
                            throw this.createFailedPredicateException("this.precpred(this.context, 2)");
                        }
                        this.state = 151;
                        localContext._op = this.tokenStream.LT(1);
                        _la = this.tokenStream.LA(1);
                        if(!(_la === 39 || _la === 40)) {
                            localContext._op = this.errorHandler.recoverInline(this);
                        }
                        else {
                            this.errorHandler.reportMatch(this);
                            this.consume();
                        }
                        this.state = 152;
                        localContext._right = this.term(3);
                        }
                        break;
                    }
                    }
                }
                this.state = 157;
                this.errorHandler.sync(this);
                alternative = this.interpreter.adaptivePredict(this.tokenStream, 10, this.context);
            }
            }
        }
        catch (re) {
            if (re instanceof antlr.RecognitionException) {
                this.errorHandler.reportError(this, re);
                this.errorHandler.recover(this, re);
            } else {
                throw re;
            }
        }
        finally {
            this.unrollRecursionContexts(parentContext);
        }
        return localContext;
    }
    public ifExpression(): IfExpressionContext {
        let localContext = new IfExpressionContext(this.context, this.state);
        this.enterRule(localContext, 22, FusionFlowParser.RULE_ifExpression);
        try {
            this.enterOuterAlt(localContext, 1);
            {
            this.state = 158;
            this.match(FusionFlowParser.IF);
            this.state = 159;
            this.match(FusionFlowParser.LPAREN);
            this.state = 160;
            this.formula(0);
            this.state = 161;
            this.match(FusionFlowParser.COMMA);
            this.state = 162;
            this.term(0);
            this.state = 163;
            this.match(FusionFlowParser.COMMA);
            this.state = 164;
            this.term(0);
            this.state = 165;
            this.match(FusionFlowParser.RPAREN);
            }
        }
        catch (re) {
            if (re instanceof antlr.RecognitionException) {
                this.errorHandler.reportError(this, re);
                this.errorHandler.recover(this, re);
            } else {
                throw re;
            }
        }
        finally {
            this.exitRule();
        }
        return localContext;
    }
    public termList(): TermListContext {
        let localContext = new TermListContext(this.context, this.state);
        this.enterRule(localContext, 24, FusionFlowParser.RULE_termList);
        let _la: number;
        try {
            this.enterOuterAlt(localContext, 1);
            {
            this.state = 167;
            this.term(0);
            this.state = 172;
            this.errorHandler.sync(this);
            _la = this.tokenStream.LA(1);
            while (_la === 50) {
                {
                {
                this.state = 168;
                this.match(FusionFlowParser.COMMA);
                this.state = 169;
                this.term(0);
                }
                }
                this.state = 174;
                this.errorHandler.sync(this);
                _la = this.tokenStream.LA(1);
            }
            }
        }
        catch (re) {
            if (re instanceof antlr.RecognitionException) {
                this.errorHandler.reportError(this, re);
                this.errorHandler.recover(this, re);
            } else {
                throw re;
            }
        }
        finally {
            this.exitRule();
        }
        return localContext;
    }
    public listLiteral(): ListLiteralContext {
        let localContext = new ListLiteralContext(this.context, this.state);
        this.enterRule(localContext, 26, FusionFlowParser.RULE_listLiteral);
        let _la: number;
        try {
            this.enterOuterAlt(localContext, 1);
            {
            this.state = 175;
            this.match(FusionFlowParser.LBRACK);
            this.state = 177;
            this.errorHandler.sync(this);
            _la = this.tokenStream.LA(1);
            if ((((_la) & ~0x1F) === 0 && ((1 << _la) & 3271557118) !== 0) || ((((_la - 39)) & ~0x1F) === 0 && ((1 << (_la - 39)) & 140099) !== 0)) {
                {
                this.state = 176;
                this.termList();
                }
            }

            this.state = 179;
            this.match(FusionFlowParser.RBRACK);
            }
        }
        catch (re) {
            if (re instanceof antlr.RecognitionException) {
                this.errorHandler.reportError(this, re);
                this.errorHandler.recover(this, re);
            } else {
                throw re;
            }
        }
        finally {
            this.exitRule();
        }
        return localContext;
    }
    public atomicTerm(): AtomicTermContext {
        let localContext = new AtomicTermContext(this.context, this.state);
        this.enterRule(localContext, 28, FusionFlowParser.RULE_atomicTerm);
        try {
            this.state = 183;
            this.errorHandler.sync(this);
            switch (this.tokenStream.LA(1)) {
            case FusionFlowParser.NUMBER:
            case FusionFlowParser.LOWID:
            case FusionFlowParser.QUOTEDCONSTANTID:
                this.enterOuterAlt(localContext, 1);
                {
                this.state = 181;
                this.constantName();
                }
                break;
            case FusionFlowParser.TRUE:
            case FusionFlowParser.FALSE:
                this.enterOuterAlt(localContext, 2);
                {
                this.state = 182;
                this.booleanLiteral();
                }
                break;
            default:
                throw new antlr.NoViableAltException(this);
            }
        }
        catch (re) {
            if (re instanceof antlr.RecognitionException) {
                this.errorHandler.reportError(this, re);
                this.errorHandler.recover(this, re);
            } else {
                throw re;
            }
        }
        finally {
            this.exitRule();
        }
        return localContext;
    }
    public identifier(): IdentifierContext {
        let localContext = new IdentifierContext(this.context, this.state);
        this.enterRule(localContext, 30, FusionFlowParser.RULE_identifier);
        try {
            this.enterOuterAlt(localContext, 1);
            {
            this.state = 185;
            this.match(FusionFlowParser.LOWID);
            }
        }
        catch (re) {
            if (re instanceof antlr.RecognitionException) {
                this.errorHandler.reportError(this, re);
                this.errorHandler.recover(this, re);
            } else {
                throw re;
            }
        }
        finally {
            this.exitRule();
        }
        return localContext;
    }
    public conceptName(): ConceptNameContext {
        let localContext = new ConceptNameContext(this.context, this.state);
        this.enterRule(localContext, 32, FusionFlowParser.RULE_conceptName);
        try {
            this.enterOuterAlt(localContext, 1);
            {
            this.state = 187;
            this.match(FusionFlowParser.UPID);
            }
        }
        catch (re) {
            if (re instanceof antlr.RecognitionException) {
                this.errorHandler.reportError(this, re);
                this.errorHandler.recover(this, re);
            } else {
                throw re;
            }
        }
        finally {
            this.exitRule();
        }
        return localContext;
    }
    public operatorName(): OperatorNameContext {
        let localContext = new OperatorNameContext(this.context, this.state);
        this.enterRule(localContext, 34, FusionFlowParser.RULE_operatorName);
        try {
            this.state = 191;
            this.errorHandler.sync(this);
            switch (this.tokenStream.LA(1)) {
            case FusionFlowParser.LOWID:
                this.enterOuterAlt(localContext, 1);
                {
                this.state = 189;
                this.match(FusionFlowParser.LOWID);
                }
                break;
            case FusionFlowParser.T__0:
            case FusionFlowParser.T__1:
            case FusionFlowParser.T__2:
            case FusionFlowParser.T__3:
            case FusionFlowParser.T__4:
            case FusionFlowParser.T__5:
            case FusionFlowParser.T__6:
            case FusionFlowParser.T__7:
            case FusionFlowParser.T__8:
            case FusionFlowParser.T__9:
            case FusionFlowParser.T__10:
            case FusionFlowParser.T__11:
            case FusionFlowParser.T__12:
            case FusionFlowParser.T__13:
            case FusionFlowParser.T__14:
            case FusionFlowParser.T__15:
            case FusionFlowParser.T__16:
            case FusionFlowParser.T__17:
            case FusionFlowParser.T__18:
            case FusionFlowParser.T__19:
            case FusionFlowParser.T__20:
            case FusionFlowParser.T__21:
            case FusionFlowParser.T__22:
                this.enterOuterAlt(localContext, 2);
                {
                this.state = 190;
                this.workflowBuiltinOperator();
                }
                break;
            default:
                throw new antlr.NoViableAltException(this);
            }
        }
        catch (re) {
            if (re instanceof antlr.RecognitionException) {
                this.errorHandler.reportError(this, re);
                this.errorHandler.recover(this, re);
            } else {
                throw re;
            }
        }
        finally {
            this.exitRule();
        }
        return localContext;
    }
    public workflowBuiltinOperator(): WorkflowBuiltinOperatorContext {
        let localContext = new WorkflowBuiltinOperatorContext(this.context, this.state);
        this.enterRule(localContext, 36, FusionFlowParser.RULE_workflowBuiltinOperator);
        try {
            this.state = 197;
            this.errorHandler.sync(this);
            switch (this.tokenStream.LA(1)) {
            case FusionFlowParser.T__0:
            case FusionFlowParser.T__1:
            case FusionFlowParser.T__2:
            case FusionFlowParser.T__3:
            case FusionFlowParser.T__4:
            case FusionFlowParser.T__5:
                this.enterOuterAlt(localContext, 1);
                {
                this.state = 193;
                this.workflowOwnerOperator();
                }
                break;
            case FusionFlowParser.T__6:
            case FusionFlowParser.T__7:
            case FusionFlowParser.T__8:
            case FusionFlowParser.T__9:
            case FusionFlowParser.T__10:
                this.enterOuterAlt(localContext, 2);
                {
                this.state = 194;
                this.stepOwnerOperator();
                }
                break;
            case FusionFlowParser.T__11:
            case FusionFlowParser.T__12:
            case FusionFlowParser.T__13:
            case FusionFlowParser.T__14:
            case FusionFlowParser.T__15:
            case FusionFlowParser.T__16:
                this.enterOuterAlt(localContext, 3);
                {
                this.state = 195;
                this.dataResourceOperator();
                }
                break;
            case FusionFlowParser.T__17:
            case FusionFlowParser.T__18:
            case FusionFlowParser.T__19:
            case FusionFlowParser.T__20:
            case FusionFlowParser.T__21:
            case FusionFlowParser.T__22:
                this.enterOuterAlt(localContext, 4);
                {
                this.state = 196;
                this.agentOwnerOperator();
                }
                break;
            default:
                throw new antlr.NoViableAltException(this);
            }
        }
        catch (re) {
            if (re instanceof antlr.RecognitionException) {
                this.errorHandler.reportError(this, re);
                this.errorHandler.recover(this, re);
            } else {
                throw re;
            }
        }
        finally {
            this.exitRule();
        }
        return localContext;
    }
    public workflowOwnerOperator(): WorkflowOwnerOperatorContext {
        let localContext = new WorkflowOwnerOperatorContext(this.context, this.state);
        this.enterRule(localContext, 38, FusionFlowParser.RULE_workflowOwnerOperator);
        let _la: number;
        try {
            this.enterOuterAlt(localContext, 1);
            {
            this.state = 199;
            _la = this.tokenStream.LA(1);
            if(!((((_la) & ~0x1F) === 0 && ((1 << _la) & 126) !== 0))) {
            this.errorHandler.recoverInline(this);
            }
            else {
                this.errorHandler.reportMatch(this);
                this.consume();
            }
            }
        }
        catch (re) {
            if (re instanceof antlr.RecognitionException) {
                this.errorHandler.reportError(this, re);
                this.errorHandler.recover(this, re);
            } else {
                throw re;
            }
        }
        finally {
            this.exitRule();
        }
        return localContext;
    }
    public stepOwnerOperator(): StepOwnerOperatorContext {
        let localContext = new StepOwnerOperatorContext(this.context, this.state);
        this.enterRule(localContext, 40, FusionFlowParser.RULE_stepOwnerOperator);
        let _la: number;
        try {
            this.enterOuterAlt(localContext, 1);
            {
            this.state = 201;
            _la = this.tokenStream.LA(1);
            if(!((((_la) & ~0x1F) === 0 && ((1 << _la) & 3968) !== 0))) {
            this.errorHandler.recoverInline(this);
            }
            else {
                this.errorHandler.reportMatch(this);
                this.consume();
            }
            }
        }
        catch (re) {
            if (re instanceof antlr.RecognitionException) {
                this.errorHandler.reportError(this, re);
                this.errorHandler.recover(this, re);
            } else {
                throw re;
            }
        }
        finally {
            this.exitRule();
        }
        return localContext;
    }
    public dataResourceOperator(): DataResourceOperatorContext {
        let localContext = new DataResourceOperatorContext(this.context, this.state);
        this.enterRule(localContext, 42, FusionFlowParser.RULE_dataResourceOperator);
        let _la: number;
        try {
            this.enterOuterAlt(localContext, 1);
            {
            this.state = 203;
            _la = this.tokenStream.LA(1);
            if(!((((_la) & ~0x1F) === 0 && ((1 << _la) & 258048) !== 0))) {
            this.errorHandler.recoverInline(this);
            }
            else {
                this.errorHandler.reportMatch(this);
                this.consume();
            }
            }
        }
        catch (re) {
            if (re instanceof antlr.RecognitionException) {
                this.errorHandler.reportError(this, re);
                this.errorHandler.recover(this, re);
            } else {
                throw re;
            }
        }
        finally {
            this.exitRule();
        }
        return localContext;
    }
    public agentOwnerOperator(): AgentOwnerOperatorContext {
        let localContext = new AgentOwnerOperatorContext(this.context, this.state);
        this.enterRule(localContext, 44, FusionFlowParser.RULE_agentOwnerOperator);
        let _la: number;
        try {
            this.enterOuterAlt(localContext, 1);
            {
            this.state = 205;
            _la = this.tokenStream.LA(1);
            if(!((((_la) & ~0x1F) === 0 && ((1 << _la) & 16515072) !== 0))) {
            this.errorHandler.recoverInline(this);
            }
            else {
                this.errorHandler.reportMatch(this);
                this.consume();
            }
            }
        }
        catch (re) {
            if (re instanceof antlr.RecognitionException) {
                this.errorHandler.reportError(this, re);
                this.errorHandler.recover(this, re);
            } else {
                throw re;
            }
        }
        finally {
            this.exitRule();
        }
        return localContext;
    }
    public constantName(): ConstantNameContext {
        let localContext = new ConstantNameContext(this.context, this.state);
        this.enterRule(localContext, 46, FusionFlowParser.RULE_constantName);
        let _la: number;
        try {
            this.enterOuterAlt(localContext, 1);
            {
            this.state = 207;
            _la = this.tokenStream.LA(1);
            if(!(((((_la - 45)) & ~0x1F) === 0 && ((1 << (_la - 45)) & 13) !== 0))) {
            this.errorHandler.recoverInline(this);
            }
            else {
                this.errorHandler.reportMatch(this);
                this.consume();
            }
            }
        }
        catch (re) {
            if (re instanceof antlr.RecognitionException) {
                this.errorHandler.reportError(this, re);
                this.errorHandler.recover(this, re);
            } else {
                throw re;
            }
        }
        finally {
            this.exitRule();
        }
        return localContext;
    }
    public booleanLiteral(): BooleanLiteralContext {
        let localContext = new BooleanLiteralContext(this.context, this.state);
        this.enterRule(localContext, 48, FusionFlowParser.RULE_booleanLiteral);
        let _la: number;
        try {
            this.enterOuterAlt(localContext, 1);
            {
            this.state = 209;
            _la = this.tokenStream.LA(1);
            if(!(_la === 30 || _la === 31)) {
            this.errorHandler.recoverInline(this);
            }
            else {
                this.errorHandler.reportMatch(this);
                this.consume();
            }
            }
        }
        catch (re) {
            if (re instanceof antlr.RecognitionException) {
                this.errorHandler.reportError(this, re);
                this.errorHandler.recover(this, re);
            } else {
                throw re;
            }
        }
        finally {
            this.exitRule();
        }
        return localContext;
    }

    public override sempred(localContext: antlr.ParserRuleContext | null, ruleIndex: number, predIndex: number): boolean {
        switch (ruleIndex) {
        case 7:
            return this.formula_sempred(localContext as FormulaContext, predIndex);
        case 10:
            return this.term_sempred(localContext as TermContext, predIndex);
        }
        return true;
    }
    private formula_sempred(localContext: FormulaContext | null, predIndex: number): boolean {
        switch (predIndex) {
        case 0:
            return this.precpred(this.context, 3);
        case 1:
            return this.precpred(this.context, 2);
        }
        return true;
    }
    private term_sempred(localContext: TermContext | null, predIndex: number): boolean {
        switch (predIndex) {
        case 2:
            return this.precpred(this.context, 4);
        case 3:
            return this.precpred(this.context, 3);
        case 4:
            return this.precpred(this.context, 2);
        }
        return true;
    }

    public static readonly _serializedATN: number[] = [
        4,1,60,212,2,0,7,0,2,1,7,1,2,2,7,2,2,3,7,3,2,4,7,4,2,5,7,5,2,6,7,
        6,2,7,7,7,2,8,7,8,2,9,7,9,2,10,7,10,2,11,7,11,2,12,7,12,2,13,7,13,
        2,14,7,14,2,15,7,15,2,16,7,16,2,17,7,17,2,18,7,18,2,19,7,19,2,20,
        7,20,2,21,7,21,2,22,7,22,2,23,7,23,2,24,7,24,1,0,1,0,1,0,5,0,54,
        8,0,10,0,12,0,57,9,0,1,0,4,0,60,8,0,11,0,12,0,61,1,0,1,0,1,1,1,1,
        1,1,1,1,5,1,70,8,1,10,1,12,1,73,9,1,1,1,1,1,1,2,1,2,1,3,1,3,1,3,
        1,4,1,4,1,4,1,4,1,4,1,5,1,5,1,5,5,5,90,8,5,10,5,12,5,93,9,5,1,6,
        1,6,1,6,1,6,1,7,1,7,1,7,1,7,1,7,1,7,1,7,1,7,3,7,107,8,7,1,7,1,7,
        1,7,1,7,1,7,1,7,5,7,115,8,7,10,7,12,7,118,9,7,1,8,1,8,1,8,1,8,1,
        9,1,9,1,10,1,10,1,10,1,10,1,10,1,10,1,10,1,10,1,10,3,10,135,8,10,
        1,10,1,10,1,10,1,10,1,10,1,10,3,10,143,8,10,1,10,1,10,1,10,1,10,
        1,10,1,10,1,10,1,10,1,10,5,10,154,8,10,10,10,12,10,157,9,10,1,11,
        1,11,1,11,1,11,1,11,1,11,1,11,1,11,1,11,1,12,1,12,1,12,5,12,171,
        8,12,10,12,12,12,174,9,12,1,13,1,13,3,13,178,8,13,1,13,1,13,1,14,
        1,14,3,14,184,8,14,1,15,1,15,1,16,1,16,1,17,1,17,3,17,192,8,17,1,
        18,1,18,1,18,1,18,3,18,198,8,18,1,19,1,19,1,20,1,20,1,21,1,21,1,
        22,1,22,1,23,1,23,1,24,1,24,1,24,0,2,14,20,25,0,2,4,6,8,10,12,14,
        16,18,20,22,24,26,28,30,32,34,36,38,40,42,44,46,48,0,9,1,0,33,38,
        1,0,39,40,1,0,41,43,1,0,1,6,1,0,7,11,1,0,12,17,1,0,18,23,2,0,45,
        45,47,48,1,0,30,31,210,0,55,1,0,0,0,2,65,1,0,0,0,4,76,1,0,0,0,6,
        78,1,0,0,0,8,81,1,0,0,0,10,86,1,0,0,0,12,94,1,0,0,0,14,106,1,0,0,
        0,16,119,1,0,0,0,18,123,1,0,0,0,20,142,1,0,0,0,22,158,1,0,0,0,24,
        167,1,0,0,0,26,175,1,0,0,0,28,183,1,0,0,0,30,185,1,0,0,0,32,187,
        1,0,0,0,34,191,1,0,0,0,36,197,1,0,0,0,38,199,1,0,0,0,40,201,1,0,
        0,0,42,203,1,0,0,0,44,205,1,0,0,0,46,207,1,0,0,0,48,209,1,0,0,0,
        50,51,3,8,4,0,51,52,5,51,0,0,52,54,1,0,0,0,53,50,1,0,0,0,54,57,1,
        0,0,0,55,53,1,0,0,0,55,56,1,0,0,0,56,59,1,0,0,0,57,55,1,0,0,0,58,
        60,3,2,1,0,59,58,1,0,0,0,60,61,1,0,0,0,61,59,1,0,0,0,61,62,1,0,0,
        0,62,63,1,0,0,0,63,64,5,0,0,1,64,1,1,0,0,0,65,66,5,24,0,0,66,67,
        3,4,2,0,67,71,5,54,0,0,68,70,3,6,3,0,69,68,1,0,0,0,70,73,1,0,0,0,
        71,69,1,0,0,0,71,72,1,0,0,0,72,74,1,0,0,0,73,71,1,0,0,0,74,75,5,
        55,0,0,75,3,1,0,0,0,76,77,3,30,15,0,77,5,1,0,0,0,78,79,3,12,6,0,
        79,80,5,51,0,0,80,7,1,0,0,0,81,82,5,26,0,0,82,83,3,46,23,0,83,84,
        5,49,0,0,84,85,3,10,5,0,85,9,1,0,0,0,86,91,3,32,16,0,87,88,5,50,
        0,0,88,90,3,32,16,0,89,87,1,0,0,0,90,93,1,0,0,0,91,89,1,0,0,0,91,
        92,1,0,0,0,92,11,1,0,0,0,93,91,1,0,0,0,94,95,3,20,10,0,95,96,5,32,
        0,0,96,97,3,20,10,0,97,13,1,0,0,0,98,99,6,7,-1,0,99,100,5,52,0,0,
        100,101,3,14,7,0,101,102,5,53,0,0,102,107,1,0,0,0,103,104,5,29,0,
        0,104,107,3,14,7,4,105,107,3,16,8,0,106,98,1,0,0,0,106,103,1,0,0,
        0,106,105,1,0,0,0,107,116,1,0,0,0,108,109,10,3,0,0,109,110,5,27,
        0,0,110,115,3,14,7,4,111,112,10,2,0,0,112,113,5,28,0,0,113,115,3,
        14,7,3,114,108,1,0,0,0,114,111,1,0,0,0,115,118,1,0,0,0,116,114,1,
        0,0,0,116,117,1,0,0,0,117,15,1,0,0,0,118,116,1,0,0,0,119,120,3,20,
        10,0,120,121,3,18,9,0,121,122,3,20,10,0,122,17,1,0,0,0,123,124,7,
        0,0,0,124,19,1,0,0,0,125,126,6,10,-1,0,126,127,5,52,0,0,127,128,
        3,20,10,0,128,129,5,53,0,0,129,143,1,0,0,0,130,143,3,22,11,0,131,
        132,3,34,17,0,132,134,5,52,0,0,133,135,3,24,12,0,134,133,1,0,0,0,
        134,135,1,0,0,0,135,136,1,0,0,0,136,137,5,53,0,0,137,143,1,0,0,0,
        138,143,3,26,13,0,139,140,7,1,0,0,140,143,3,20,10,5,141,143,3,28,
        14,0,142,125,1,0,0,0,142,130,1,0,0,0,142,131,1,0,0,0,142,138,1,0,
        0,0,142,139,1,0,0,0,142,141,1,0,0,0,143,155,1,0,0,0,144,145,10,4,
        0,0,145,146,5,44,0,0,146,154,3,20,10,4,147,148,10,3,0,0,148,149,
        7,2,0,0,149,154,3,20,10,4,150,151,10,2,0,0,151,152,7,1,0,0,152,154,
        3,20,10,3,153,144,1,0,0,0,153,147,1,0,0,0,153,150,1,0,0,0,154,157,
        1,0,0,0,155,153,1,0,0,0,155,156,1,0,0,0,156,21,1,0,0,0,157,155,1,
        0,0,0,158,159,5,25,0,0,159,160,5,52,0,0,160,161,3,14,7,0,161,162,
        5,50,0,0,162,163,3,20,10,0,163,164,5,50,0,0,164,165,3,20,10,0,165,
        166,5,53,0,0,166,23,1,0,0,0,167,172,3,20,10,0,168,169,5,50,0,0,169,
        171,3,20,10,0,170,168,1,0,0,0,171,174,1,0,0,0,172,170,1,0,0,0,172,
        173,1,0,0,0,173,25,1,0,0,0,174,172,1,0,0,0,175,177,5,56,0,0,176,
        178,3,24,12,0,177,176,1,0,0,0,177,178,1,0,0,0,178,179,1,0,0,0,179,
        180,5,57,0,0,180,27,1,0,0,0,181,184,3,46,23,0,182,184,3,48,24,0,
        183,181,1,0,0,0,183,182,1,0,0,0,184,29,1,0,0,0,185,186,5,47,0,0,
        186,31,1,0,0,0,187,188,5,46,0,0,188,33,1,0,0,0,189,192,5,47,0,0,
        190,192,3,36,18,0,191,189,1,0,0,0,191,190,1,0,0,0,192,35,1,0,0,0,
        193,198,3,38,19,0,194,198,3,40,20,0,195,198,3,42,21,0,196,198,3,
        44,22,0,197,193,1,0,0,0,197,194,1,0,0,0,197,195,1,0,0,0,197,196,
        1,0,0,0,198,37,1,0,0,0,199,200,7,3,0,0,200,39,1,0,0,0,201,202,7,
        4,0,0,202,41,1,0,0,0,203,204,7,5,0,0,204,43,1,0,0,0,205,206,7,6,
        0,0,206,45,1,0,0,0,207,208,7,7,0,0,208,47,1,0,0,0,209,210,7,8,0,
        0,210,49,1,0,0,0,16,55,61,71,91,106,114,116,134,142,153,155,172,
        177,183,191,197
    ];

    private static __ATN: antlr.ATN;
    public static get _ATN(): antlr.ATN {
        if (!FusionFlowParser.__ATN) {
            FusionFlowParser.__ATN = new antlr.ATNDeserializer().deserialize(FusionFlowParser._serializedATN);
        }

        return FusionFlowParser.__ATN;
    }


    private static readonly vocabulary = new antlr.Vocabulary(FusionFlowParser.literalNames, FusionFlowParser.symbolicNames, []);

    public override get vocabulary(): antlr.Vocabulary {
        return FusionFlowParser.vocabulary;
    }

    private static readonly decisionsToDFA = FusionFlowParser._ATN.decisionToState.map( (ds: antlr.DecisionState, index: number) => new antlr.DFA(ds, index) );
}

export class WorkflowFileContext extends antlr.ParserRuleContext {
    public constructor(parent: antlr.ParserRuleContext | null, invokingState: number) {
        super(parent, invokingState);
    }
    public EOF(): antlr.TerminalNode {
        return this.getToken(FusionFlowParser.EOF, 0)!;
    }
    public constDecl(): ConstDeclContext[];
    public constDecl(i: number): ConstDeclContext | null;
    public constDecl(i?: number): ConstDeclContext[] | ConstDeclContext | null {
        if (i === undefined) {
            return this.getRuleContexts(ConstDeclContext);
        }

        return this.getRuleContext(i, ConstDeclContext);
    }
    public SEMICOLON(): antlr.TerminalNode[];
    public SEMICOLON(i: number): antlr.TerminalNode | null;
    public SEMICOLON(i?: number): antlr.TerminalNode | null | antlr.TerminalNode[] {
    	if (i === undefined) {
    		return this.getTokens(FusionFlowParser.SEMICOLON);
    	} else {
    		return this.getToken(FusionFlowParser.SEMICOLON, i);
    	}
    }
    public workflowDecl(): WorkflowDeclContext[];
    public workflowDecl(i: number): WorkflowDeclContext | null;
    public workflowDecl(i?: number): WorkflowDeclContext[] | WorkflowDeclContext | null {
        if (i === undefined) {
            return this.getRuleContexts(WorkflowDeclContext);
        }

        return this.getRuleContext(i, WorkflowDeclContext);
    }
    public override get ruleIndex(): number {
        return FusionFlowParser.RULE_workflowFile;
    }
    public override accept<Result>(visitor: FusionFlowVisitor<Result>): Result | null {
        if (visitor.visitWorkflowFile) {
            return visitor.visitWorkflowFile(this);
        } else {
            return visitor.visitChildren(this);
        }
    }
}


export class WorkflowDeclContext extends antlr.ParserRuleContext {
    public constructor(parent: antlr.ParserRuleContext | null, invokingState: number) {
        super(parent, invokingState);
    }
    public WORKFLOW(): antlr.TerminalNode {
        return this.getToken(FusionFlowParser.WORKFLOW, 0)!;
    }
    public workflowName(): WorkflowNameContext {
        return this.getRuleContext(0, WorkflowNameContext)!;
    }
    public LBRACE(): antlr.TerminalNode {
        return this.getToken(FusionFlowParser.LBRACE, 0)!;
    }
    public RBRACE(): antlr.TerminalNode {
        return this.getToken(FusionFlowParser.RBRACE, 0)!;
    }
    public workflowItem(): WorkflowItemContext[];
    public workflowItem(i: number): WorkflowItemContext | null;
    public workflowItem(i?: number): WorkflowItemContext[] | WorkflowItemContext | null {
        if (i === undefined) {
            return this.getRuleContexts(WorkflowItemContext);
        }

        return this.getRuleContext(i, WorkflowItemContext);
    }
    public override get ruleIndex(): number {
        return FusionFlowParser.RULE_workflowDecl;
    }
    public override accept<Result>(visitor: FusionFlowVisitor<Result>): Result | null {
        if (visitor.visitWorkflowDecl) {
            return visitor.visitWorkflowDecl(this);
        } else {
            return visitor.visitChildren(this);
        }
    }
}


export class WorkflowNameContext extends antlr.ParserRuleContext {
    public constructor(parent: antlr.ParserRuleContext | null, invokingState: number) {
        super(parent, invokingState);
    }
    public identifier(): IdentifierContext {
        return this.getRuleContext(0, IdentifierContext)!;
    }
    public override get ruleIndex(): number {
        return FusionFlowParser.RULE_workflowName;
    }
    public override accept<Result>(visitor: FusionFlowVisitor<Result>): Result | null {
        if (visitor.visitWorkflowName) {
            return visitor.visitWorkflowName(this);
        } else {
            return visitor.visitChildren(this);
        }
    }
}


export class WorkflowItemContext extends antlr.ParserRuleContext {
    public constructor(parent: antlr.ParserRuleContext | null, invokingState: number) {
        super(parent, invokingState);
    }
    public assertion(): AssertionContext {
        return this.getRuleContext(0, AssertionContext)!;
    }
    public SEMICOLON(): antlr.TerminalNode {
        return this.getToken(FusionFlowParser.SEMICOLON, 0)!;
    }
    public override get ruleIndex(): number {
        return FusionFlowParser.RULE_workflowItem;
    }
    public override accept<Result>(visitor: FusionFlowVisitor<Result>): Result | null {
        if (visitor.visitWorkflowItem) {
            return visitor.visitWorkflowItem(this);
        } else {
            return visitor.visitChildren(this);
        }
    }
}


export class ConstDeclContext extends antlr.ParserRuleContext {
    public constructor(parent: antlr.ParserRuleContext | null, invokingState: number) {
        super(parent, invokingState);
    }
    public CONST(): antlr.TerminalNode {
        return this.getToken(FusionFlowParser.CONST, 0)!;
    }
    public constantName(): ConstantNameContext {
        return this.getRuleContext(0, ConstantNameContext)!;
    }
    public COLON(): antlr.TerminalNode {
        return this.getToken(FusionFlowParser.COLON, 0)!;
    }
    public conceptNameList(): ConceptNameListContext {
        return this.getRuleContext(0, ConceptNameListContext)!;
    }
    public override get ruleIndex(): number {
        return FusionFlowParser.RULE_constDecl;
    }
    public override accept<Result>(visitor: FusionFlowVisitor<Result>): Result | null {
        if (visitor.visitConstDecl) {
            return visitor.visitConstDecl(this);
        } else {
            return visitor.visitChildren(this);
        }
    }
}


export class ConceptNameListContext extends antlr.ParserRuleContext {
    public constructor(parent: antlr.ParserRuleContext | null, invokingState: number) {
        super(parent, invokingState);
    }
    public conceptName(): ConceptNameContext[];
    public conceptName(i: number): ConceptNameContext | null;
    public conceptName(i?: number): ConceptNameContext[] | ConceptNameContext | null {
        if (i === undefined) {
            return this.getRuleContexts(ConceptNameContext);
        }

        return this.getRuleContext(i, ConceptNameContext);
    }
    public COMMA(): antlr.TerminalNode[];
    public COMMA(i: number): antlr.TerminalNode | null;
    public COMMA(i?: number): antlr.TerminalNode | null | antlr.TerminalNode[] {
    	if (i === undefined) {
    		return this.getTokens(FusionFlowParser.COMMA);
    	} else {
    		return this.getToken(FusionFlowParser.COMMA, i);
    	}
    }
    public override get ruleIndex(): number {
        return FusionFlowParser.RULE_conceptNameList;
    }
    public override accept<Result>(visitor: FusionFlowVisitor<Result>): Result | null {
        if (visitor.visitConceptNameList) {
            return visitor.visitConceptNameList(this);
        } else {
            return visitor.visitChildren(this);
        }
    }
}


export class AssertionContext extends antlr.ParserRuleContext {
    public constructor(parent: antlr.ParserRuleContext | null, invokingState: number) {
        super(parent, invokingState);
    }
    public term(): TermContext[];
    public term(i: number): TermContext | null;
    public term(i?: number): TermContext[] | TermContext | null {
        if (i === undefined) {
            return this.getRuleContexts(TermContext);
        }

        return this.getRuleContext(i, TermContext);
    }
    public ASSERT_EQ(): antlr.TerminalNode {
        return this.getToken(FusionFlowParser.ASSERT_EQ, 0)!;
    }
    public override get ruleIndex(): number {
        return FusionFlowParser.RULE_assertion;
    }
    public override accept<Result>(visitor: FusionFlowVisitor<Result>): Result | null {
        if (visitor.visitAssertion) {
            return visitor.visitAssertion(this);
        } else {
            return visitor.visitChildren(this);
        }
    }
}


export class FormulaContext extends antlr.ParserRuleContext {
    public _left?: FormulaContext;
    public _right?: FormulaContext;
    public constructor(parent: antlr.ParserRuleContext | null, invokingState: number) {
        super(parent, invokingState);
    }
    public LPAREN(): antlr.TerminalNode | null {
        return this.getToken(FusionFlowParser.LPAREN, 0);
    }
    public formula(): FormulaContext[];
    public formula(i: number): FormulaContext | null;
    public formula(i?: number): FormulaContext[] | FormulaContext | null {
        if (i === undefined) {
            return this.getRuleContexts(FormulaContext);
        }

        return this.getRuleContext(i, FormulaContext);
    }
    public RPAREN(): antlr.TerminalNode | null {
        return this.getToken(FusionFlowParser.RPAREN, 0);
    }
    public NOT(): antlr.TerminalNode | null {
        return this.getToken(FusionFlowParser.NOT, 0);
    }
    public comparison(): ComparisonContext | null {
        return this.getRuleContext(0, ComparisonContext);
    }
    public AND(): antlr.TerminalNode | null {
        return this.getToken(FusionFlowParser.AND, 0);
    }
    public OR(): antlr.TerminalNode | null {
        return this.getToken(FusionFlowParser.OR, 0);
    }
    public override get ruleIndex(): number {
        return FusionFlowParser.RULE_formula;
    }
    public override accept<Result>(visitor: FusionFlowVisitor<Result>): Result | null {
        if (visitor.visitFormula) {
            return visitor.visitFormula(this);
        } else {
            return visitor.visitChildren(this);
        }
    }
}


export class ComparisonContext extends antlr.ParserRuleContext {
    public constructor(parent: antlr.ParserRuleContext | null, invokingState: number) {
        super(parent, invokingState);
    }
    public term(): TermContext[];
    public term(i: number): TermContext | null;
    public term(i?: number): TermContext[] | TermContext | null {
        if (i === undefined) {
            return this.getRuleContexts(TermContext);
        }

        return this.getRuleContext(i, TermContext);
    }
    public comparisonOp(): ComparisonOpContext {
        return this.getRuleContext(0, ComparisonOpContext)!;
    }
    public override get ruleIndex(): number {
        return FusionFlowParser.RULE_comparison;
    }
    public override accept<Result>(visitor: FusionFlowVisitor<Result>): Result | null {
        if (visitor.visitComparison) {
            return visitor.visitComparison(this);
        } else {
            return visitor.visitChildren(this);
        }
    }
}


export class ComparisonOpContext extends antlr.ParserRuleContext {
    public constructor(parent: antlr.ParserRuleContext | null, invokingState: number) {
        super(parent, invokingState);
    }
    public NUMERIC_EQ(): antlr.TerminalNode | null {
        return this.getToken(FusionFlowParser.NUMERIC_EQ, 0);
    }
    public NOT_EQUALS(): antlr.TerminalNode | null {
        return this.getToken(FusionFlowParser.NOT_EQUALS, 0);
    }
    public LT(): antlr.TerminalNode | null {
        return this.getToken(FusionFlowParser.LT, 0);
    }
    public LTE(): antlr.TerminalNode | null {
        return this.getToken(FusionFlowParser.LTE, 0);
    }
    public GT(): antlr.TerminalNode | null {
        return this.getToken(FusionFlowParser.GT, 0);
    }
    public GTE(): antlr.TerminalNode | null {
        return this.getToken(FusionFlowParser.GTE, 0);
    }
    public override get ruleIndex(): number {
        return FusionFlowParser.RULE_comparisonOp;
    }
    public override accept<Result>(visitor: FusionFlowVisitor<Result>): Result | null {
        if (visitor.visitComparisonOp) {
            return visitor.visitComparisonOp(this);
        } else {
            return visitor.visitChildren(this);
        }
    }
}


export class TermContext extends antlr.ParserRuleContext {
    public _left?: TermContext;
    public _op?: Token | null;
    public _right?: TermContext;
    public constructor(parent: antlr.ParserRuleContext | null, invokingState: number) {
        super(parent, invokingState);
    }
    public LPAREN(): antlr.TerminalNode | null {
        return this.getToken(FusionFlowParser.LPAREN, 0);
    }
    public term(): TermContext[];
    public term(i: number): TermContext | null;
    public term(i?: number): TermContext[] | TermContext | null {
        if (i === undefined) {
            return this.getRuleContexts(TermContext);
        }

        return this.getRuleContext(i, TermContext);
    }
    public RPAREN(): antlr.TerminalNode | null {
        return this.getToken(FusionFlowParser.RPAREN, 0);
    }
    public ifExpression(): IfExpressionContext | null {
        return this.getRuleContext(0, IfExpressionContext);
    }
    public operatorName(): OperatorNameContext | null {
        return this.getRuleContext(0, OperatorNameContext);
    }
    public termList(): TermListContext | null {
        return this.getRuleContext(0, TermListContext);
    }
    public listLiteral(): ListLiteralContext | null {
        return this.getRuleContext(0, ListLiteralContext);
    }
    public PLUS(): antlr.TerminalNode | null {
        return this.getToken(FusionFlowParser.PLUS, 0);
    }
    public MINUS(): antlr.TerminalNode | null {
        return this.getToken(FusionFlowParser.MINUS, 0);
    }
    public atomicTerm(): AtomicTermContext | null {
        return this.getRuleContext(0, AtomicTermContext);
    }
    public CARET(): antlr.TerminalNode | null {
        return this.getToken(FusionFlowParser.CARET, 0);
    }
    public STAR(): antlr.TerminalNode | null {
        return this.getToken(FusionFlowParser.STAR, 0);
    }
    public DIVIDE(): antlr.TerminalNode | null {
        return this.getToken(FusionFlowParser.DIVIDE, 0);
    }
    public MODULO(): antlr.TerminalNode | null {
        return this.getToken(FusionFlowParser.MODULO, 0);
    }
    public override get ruleIndex(): number {
        return FusionFlowParser.RULE_term;
    }
    public override accept<Result>(visitor: FusionFlowVisitor<Result>): Result | null {
        if (visitor.visitTerm) {
            return visitor.visitTerm(this);
        } else {
            return visitor.visitChildren(this);
        }
    }
}


export class IfExpressionContext extends antlr.ParserRuleContext {
    public constructor(parent: antlr.ParserRuleContext | null, invokingState: number) {
        super(parent, invokingState);
    }
    public IF(): antlr.TerminalNode {
        return this.getToken(FusionFlowParser.IF, 0)!;
    }
    public LPAREN(): antlr.TerminalNode {
        return this.getToken(FusionFlowParser.LPAREN, 0)!;
    }
    public formula(): FormulaContext {
        return this.getRuleContext(0, FormulaContext)!;
    }
    public COMMA(): antlr.TerminalNode[];
    public COMMA(i: number): antlr.TerminalNode | null;
    public COMMA(i?: number): antlr.TerminalNode | null | antlr.TerminalNode[] {
    	if (i === undefined) {
    		return this.getTokens(FusionFlowParser.COMMA);
    	} else {
    		return this.getToken(FusionFlowParser.COMMA, i);
    	}
    }
    public term(): TermContext[];
    public term(i: number): TermContext | null;
    public term(i?: number): TermContext[] | TermContext | null {
        if (i === undefined) {
            return this.getRuleContexts(TermContext);
        }

        return this.getRuleContext(i, TermContext);
    }
    public RPAREN(): antlr.TerminalNode {
        return this.getToken(FusionFlowParser.RPAREN, 0)!;
    }
    public override get ruleIndex(): number {
        return FusionFlowParser.RULE_ifExpression;
    }
    public override accept<Result>(visitor: FusionFlowVisitor<Result>): Result | null {
        if (visitor.visitIfExpression) {
            return visitor.visitIfExpression(this);
        } else {
            return visitor.visitChildren(this);
        }
    }
}


export class TermListContext extends antlr.ParserRuleContext {
    public constructor(parent: antlr.ParserRuleContext | null, invokingState: number) {
        super(parent, invokingState);
    }
    public term(): TermContext[];
    public term(i: number): TermContext | null;
    public term(i?: number): TermContext[] | TermContext | null {
        if (i === undefined) {
            return this.getRuleContexts(TermContext);
        }

        return this.getRuleContext(i, TermContext);
    }
    public COMMA(): antlr.TerminalNode[];
    public COMMA(i: number): antlr.TerminalNode | null;
    public COMMA(i?: number): antlr.TerminalNode | null | antlr.TerminalNode[] {
    	if (i === undefined) {
    		return this.getTokens(FusionFlowParser.COMMA);
    	} else {
    		return this.getToken(FusionFlowParser.COMMA, i);
    	}
    }
    public override get ruleIndex(): number {
        return FusionFlowParser.RULE_termList;
    }
    public override accept<Result>(visitor: FusionFlowVisitor<Result>): Result | null {
        if (visitor.visitTermList) {
            return visitor.visitTermList(this);
        } else {
            return visitor.visitChildren(this);
        }
    }
}


export class ListLiteralContext extends antlr.ParserRuleContext {
    public constructor(parent: antlr.ParserRuleContext | null, invokingState: number) {
        super(parent, invokingState);
    }
    public LBRACK(): antlr.TerminalNode {
        return this.getToken(FusionFlowParser.LBRACK, 0)!;
    }
    public RBRACK(): antlr.TerminalNode {
        return this.getToken(FusionFlowParser.RBRACK, 0)!;
    }
    public termList(): TermListContext | null {
        return this.getRuleContext(0, TermListContext);
    }
    public override get ruleIndex(): number {
        return FusionFlowParser.RULE_listLiteral;
    }
    public override accept<Result>(visitor: FusionFlowVisitor<Result>): Result | null {
        if (visitor.visitListLiteral) {
            return visitor.visitListLiteral(this);
        } else {
            return visitor.visitChildren(this);
        }
    }
}


export class AtomicTermContext extends antlr.ParserRuleContext {
    public constructor(parent: antlr.ParserRuleContext | null, invokingState: number) {
        super(parent, invokingState);
    }
    public constantName(): ConstantNameContext | null {
        return this.getRuleContext(0, ConstantNameContext);
    }
    public booleanLiteral(): BooleanLiteralContext | null {
        return this.getRuleContext(0, BooleanLiteralContext);
    }
    public override get ruleIndex(): number {
        return FusionFlowParser.RULE_atomicTerm;
    }
    public override accept<Result>(visitor: FusionFlowVisitor<Result>): Result | null {
        if (visitor.visitAtomicTerm) {
            return visitor.visitAtomicTerm(this);
        } else {
            return visitor.visitChildren(this);
        }
    }
}


export class IdentifierContext extends antlr.ParserRuleContext {
    public constructor(parent: antlr.ParserRuleContext | null, invokingState: number) {
        super(parent, invokingState);
    }
    public LOWID(): antlr.TerminalNode {
        return this.getToken(FusionFlowParser.LOWID, 0)!;
    }
    public override get ruleIndex(): number {
        return FusionFlowParser.RULE_identifier;
    }
    public override accept<Result>(visitor: FusionFlowVisitor<Result>): Result | null {
        if (visitor.visitIdentifier) {
            return visitor.visitIdentifier(this);
        } else {
            return visitor.visitChildren(this);
        }
    }
}


export class ConceptNameContext extends antlr.ParserRuleContext {
    public constructor(parent: antlr.ParserRuleContext | null, invokingState: number) {
        super(parent, invokingState);
    }
    public UPID(): antlr.TerminalNode {
        return this.getToken(FusionFlowParser.UPID, 0)!;
    }
    public override get ruleIndex(): number {
        return FusionFlowParser.RULE_conceptName;
    }
    public override accept<Result>(visitor: FusionFlowVisitor<Result>): Result | null {
        if (visitor.visitConceptName) {
            return visitor.visitConceptName(this);
        } else {
            return visitor.visitChildren(this);
        }
    }
}


export class OperatorNameContext extends antlr.ParserRuleContext {
    public constructor(parent: antlr.ParserRuleContext | null, invokingState: number) {
        super(parent, invokingState);
    }
    public LOWID(): antlr.TerminalNode | null {
        return this.getToken(FusionFlowParser.LOWID, 0);
    }
    public workflowBuiltinOperator(): WorkflowBuiltinOperatorContext | null {
        return this.getRuleContext(0, WorkflowBuiltinOperatorContext);
    }
    public override get ruleIndex(): number {
        return FusionFlowParser.RULE_operatorName;
    }
    public override accept<Result>(visitor: FusionFlowVisitor<Result>): Result | null {
        if (visitor.visitOperatorName) {
            return visitor.visitOperatorName(this);
        } else {
            return visitor.visitChildren(this);
        }
    }
}


export class WorkflowBuiltinOperatorContext extends antlr.ParserRuleContext {
    public constructor(parent: antlr.ParserRuleContext | null, invokingState: number) {
        super(parent, invokingState);
    }
    public workflowOwnerOperator(): WorkflowOwnerOperatorContext | null {
        return this.getRuleContext(0, WorkflowOwnerOperatorContext);
    }
    public stepOwnerOperator(): StepOwnerOperatorContext | null {
        return this.getRuleContext(0, StepOwnerOperatorContext);
    }
    public dataResourceOperator(): DataResourceOperatorContext | null {
        return this.getRuleContext(0, DataResourceOperatorContext);
    }
    public agentOwnerOperator(): AgentOwnerOperatorContext | null {
        return this.getRuleContext(0, AgentOwnerOperatorContext);
    }
    public override get ruleIndex(): number {
        return FusionFlowParser.RULE_workflowBuiltinOperator;
    }
    public override accept<Result>(visitor: FusionFlowVisitor<Result>): Result | null {
        if (visitor.visitWorkflowBuiltinOperator) {
            return visitor.visitWorkflowBuiltinOperator(this);
        } else {
            return visitor.visitChildren(this);
        }
    }
}


export class WorkflowOwnerOperatorContext extends antlr.ParserRuleContext {
    public constructor(parent: antlr.ParserRuleContext | null, invokingState: number) {
        super(parent, invokingState);
    }
    public override get ruleIndex(): number {
        return FusionFlowParser.RULE_workflowOwnerOperator;
    }
    public override accept<Result>(visitor: FusionFlowVisitor<Result>): Result | null {
        if (visitor.visitWorkflowOwnerOperator) {
            return visitor.visitWorkflowOwnerOperator(this);
        } else {
            return visitor.visitChildren(this);
        }
    }
}


export class StepOwnerOperatorContext extends antlr.ParserRuleContext {
    public constructor(parent: antlr.ParserRuleContext | null, invokingState: number) {
        super(parent, invokingState);
    }
    public override get ruleIndex(): number {
        return FusionFlowParser.RULE_stepOwnerOperator;
    }
    public override accept<Result>(visitor: FusionFlowVisitor<Result>): Result | null {
        if (visitor.visitStepOwnerOperator) {
            return visitor.visitStepOwnerOperator(this);
        } else {
            return visitor.visitChildren(this);
        }
    }
}


export class DataResourceOperatorContext extends antlr.ParserRuleContext {
    public constructor(parent: antlr.ParserRuleContext | null, invokingState: number) {
        super(parent, invokingState);
    }
    public override get ruleIndex(): number {
        return FusionFlowParser.RULE_dataResourceOperator;
    }
    public override accept<Result>(visitor: FusionFlowVisitor<Result>): Result | null {
        if (visitor.visitDataResourceOperator) {
            return visitor.visitDataResourceOperator(this);
        } else {
            return visitor.visitChildren(this);
        }
    }
}


export class AgentOwnerOperatorContext extends antlr.ParserRuleContext {
    public constructor(parent: antlr.ParserRuleContext | null, invokingState: number) {
        super(parent, invokingState);
    }
    public override get ruleIndex(): number {
        return FusionFlowParser.RULE_agentOwnerOperator;
    }
    public override accept<Result>(visitor: FusionFlowVisitor<Result>): Result | null {
        if (visitor.visitAgentOwnerOperator) {
            return visitor.visitAgentOwnerOperator(this);
        } else {
            return visitor.visitChildren(this);
        }
    }
}


export class ConstantNameContext extends antlr.ParserRuleContext {
    public constructor(parent: antlr.ParserRuleContext | null, invokingState: number) {
        super(parent, invokingState);
    }
    public NUMBER(): antlr.TerminalNode | null {
        return this.getToken(FusionFlowParser.NUMBER, 0);
    }
    public QUOTEDCONSTANTID(): antlr.TerminalNode | null {
        return this.getToken(FusionFlowParser.QUOTEDCONSTANTID, 0);
    }
    public LOWID(): antlr.TerminalNode | null {
        return this.getToken(FusionFlowParser.LOWID, 0);
    }
    public override get ruleIndex(): number {
        return FusionFlowParser.RULE_constantName;
    }
    public override accept<Result>(visitor: FusionFlowVisitor<Result>): Result | null {
        if (visitor.visitConstantName) {
            return visitor.visitConstantName(this);
        } else {
            return visitor.visitChildren(this);
        }
    }
}


export class BooleanLiteralContext extends antlr.ParserRuleContext {
    public constructor(parent: antlr.ParserRuleContext | null, invokingState: number) {
        super(parent, invokingState);
    }
    public TRUE(): antlr.TerminalNode | null {
        return this.getToken(FusionFlowParser.TRUE, 0);
    }
    public FALSE(): antlr.TerminalNode | null {
        return this.getToken(FusionFlowParser.FALSE, 0);
    }
    public override get ruleIndex(): number {
        return FusionFlowParser.RULE_booleanLiteral;
    }
    public override accept<Result>(visitor: FusionFlowVisitor<Result>): Result | null {
        if (visitor.visitBooleanLiteral) {
            return visitor.visitBooleanLiteral(this);
        } else {
            return visitor.visitChildren(this);
        }
    }
}
