
import { AbstractParseTreeVisitor } from "antlr4ng";


import { WorkflowFileContext } from "./FusionFlowParser.js";
import { WorkflowDeclContext } from "./FusionFlowParser.js";
import { WorkflowNameContext } from "./FusionFlowParser.js";
import { WorkflowItemContext } from "./FusionFlowParser.js";
import { ConstDeclContext } from "./FusionFlowParser.js";
import { ConceptNameListContext } from "./FusionFlowParser.js";
import { AssertionContext } from "./FusionFlowParser.js";
import { FormulaContext } from "./FusionFlowParser.js";
import { ComparisonContext } from "./FusionFlowParser.js";
import { ComparisonOpContext } from "./FusionFlowParser.js";
import { TermContext } from "./FusionFlowParser.js";
import { IfExpressionContext } from "./FusionFlowParser.js";
import { TermListContext } from "./FusionFlowParser.js";
import { ListLiteralContext } from "./FusionFlowParser.js";
import { AtomicTermContext } from "./FusionFlowParser.js";
import { IdentifierContext } from "./FusionFlowParser.js";
import { ConceptNameContext } from "./FusionFlowParser.js";
import { OperatorNameContext } from "./FusionFlowParser.js";
import { WorkflowBuiltinOperatorContext } from "./FusionFlowParser.js";
import { WorkflowOwnerOperatorContext } from "./FusionFlowParser.js";
import { StepOwnerOperatorContext } from "./FusionFlowParser.js";
import { DataResourceOperatorContext } from "./FusionFlowParser.js";
import { AgentOwnerOperatorContext } from "./FusionFlowParser.js";
import { ConstantNameContext } from "./FusionFlowParser.js";
import { BooleanLiteralContext } from "./FusionFlowParser.js";


/**
 * This interface defines a complete generic visitor for a parse tree produced
 * by `FusionFlowParser`.
 *
 * @param <Result> The return type of the visit operation. Use `void` for
 * operations with no return type.
 */
export class FusionFlowVisitor<Result> extends AbstractParseTreeVisitor<Result> {
    /**
     * Visit a parse tree produced by `FusionFlowParser.workflowFile`.
     * @param ctx the parse tree
     * @return the visitor result
     */
    visitWorkflowFile?: (ctx: WorkflowFileContext) => Result;
    /**
     * Visit a parse tree produced by `FusionFlowParser.workflowDecl`.
     * @param ctx the parse tree
     * @return the visitor result
     */
    visitWorkflowDecl?: (ctx: WorkflowDeclContext) => Result;
    /**
     * Visit a parse tree produced by `FusionFlowParser.workflowName`.
     * @param ctx the parse tree
     * @return the visitor result
     */
    visitWorkflowName?: (ctx: WorkflowNameContext) => Result;
    /**
     * Visit a parse tree produced by `FusionFlowParser.workflowItem`.
     * @param ctx the parse tree
     * @return the visitor result
     */
    visitWorkflowItem?: (ctx: WorkflowItemContext) => Result;
    /**
     * Visit a parse tree produced by `FusionFlowParser.constDecl`.
     * @param ctx the parse tree
     * @return the visitor result
     */
    visitConstDecl?: (ctx: ConstDeclContext) => Result;
    /**
     * Visit a parse tree produced by `FusionFlowParser.conceptNameList`.
     * @param ctx the parse tree
     * @return the visitor result
     */
    visitConceptNameList?: (ctx: ConceptNameListContext) => Result;
    /**
     * Visit a parse tree produced by `FusionFlowParser.assertion`.
     * @param ctx the parse tree
     * @return the visitor result
     */
    visitAssertion?: (ctx: AssertionContext) => Result;
    /**
     * Visit a parse tree produced by `FusionFlowParser.formula`.
     * @param ctx the parse tree
     * @return the visitor result
     */
    visitFormula?: (ctx: FormulaContext) => Result;
    /**
     * Visit a parse tree produced by `FusionFlowParser.comparison`.
     * @param ctx the parse tree
     * @return the visitor result
     */
    visitComparison?: (ctx: ComparisonContext) => Result;
    /**
     * Visit a parse tree produced by `FusionFlowParser.comparisonOp`.
     * @param ctx the parse tree
     * @return the visitor result
     */
    visitComparisonOp?: (ctx: ComparisonOpContext) => Result;
    /**
     * Visit a parse tree produced by `FusionFlowParser.term`.
     * @param ctx the parse tree
     * @return the visitor result
     */
    visitTerm?: (ctx: TermContext) => Result;
    /**
     * Visit a parse tree produced by `FusionFlowParser.ifExpression`.
     * @param ctx the parse tree
     * @return the visitor result
     */
    visitIfExpression?: (ctx: IfExpressionContext) => Result;
    /**
     * Visit a parse tree produced by `FusionFlowParser.termList`.
     * @param ctx the parse tree
     * @return the visitor result
     */
    visitTermList?: (ctx: TermListContext) => Result;
    /**
     * Visit a parse tree produced by `FusionFlowParser.listLiteral`.
     * @param ctx the parse tree
     * @return the visitor result
     */
    visitListLiteral?: (ctx: ListLiteralContext) => Result;
    /**
     * Visit a parse tree produced by `FusionFlowParser.atomicTerm`.
     * @param ctx the parse tree
     * @return the visitor result
     */
    visitAtomicTerm?: (ctx: AtomicTermContext) => Result;
    /**
     * Visit a parse tree produced by `FusionFlowParser.identifier`.
     * @param ctx the parse tree
     * @return the visitor result
     */
    visitIdentifier?: (ctx: IdentifierContext) => Result;
    /**
     * Visit a parse tree produced by `FusionFlowParser.conceptName`.
     * @param ctx the parse tree
     * @return the visitor result
     */
    visitConceptName?: (ctx: ConceptNameContext) => Result;
    /**
     * Visit a parse tree produced by `FusionFlowParser.operatorName`.
     * @param ctx the parse tree
     * @return the visitor result
     */
    visitOperatorName?: (ctx: OperatorNameContext) => Result;
    /**
     * Visit a parse tree produced by `FusionFlowParser.workflowBuiltinOperator`.
     * @param ctx the parse tree
     * @return the visitor result
     */
    visitWorkflowBuiltinOperator?: (ctx: WorkflowBuiltinOperatorContext) => Result;
    /**
     * Visit a parse tree produced by `FusionFlowParser.workflowOwnerOperator`.
     * @param ctx the parse tree
     * @return the visitor result
     */
    visitWorkflowOwnerOperator?: (ctx: WorkflowOwnerOperatorContext) => Result;
    /**
     * Visit a parse tree produced by `FusionFlowParser.stepOwnerOperator`.
     * @param ctx the parse tree
     * @return the visitor result
     */
    visitStepOwnerOperator?: (ctx: StepOwnerOperatorContext) => Result;
    /**
     * Visit a parse tree produced by `FusionFlowParser.dataResourceOperator`.
     * @param ctx the parse tree
     * @return the visitor result
     */
    visitDataResourceOperator?: (ctx: DataResourceOperatorContext) => Result;
    /**
     * Visit a parse tree produced by `FusionFlowParser.agentOwnerOperator`.
     * @param ctx the parse tree
     * @return the visitor result
     */
    visitAgentOwnerOperator?: (ctx: AgentOwnerOperatorContext) => Result;
    /**
     * Visit a parse tree produced by `FusionFlowParser.constantName`.
     * @param ctx the parse tree
     * @return the visitor result
     */
    visitConstantName?: (ctx: ConstantNameContext) => Result;
    /**
     * Visit a parse tree produced by `FusionFlowParser.booleanLiteral`.
     * @param ctx the parse tree
     * @return the visitor result
     */
    visitBooleanLiteral?: (ctx: BooleanLiteralContext) => Result;
}

