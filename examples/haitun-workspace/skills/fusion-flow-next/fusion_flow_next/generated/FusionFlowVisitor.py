# Generated from grammar/FusionFlow.g4 by ANTLR 4.13.2
from antlr4 import *
if "." in __name__:
    from .FusionFlowParser import FusionFlowParser
else:
    from FusionFlowParser import FusionFlowParser

# This class defines a complete generic visitor for a parse tree produced by FusionFlowParser.

class FusionFlowVisitor(ParseTreeVisitor):

    # Visit a parse tree produced by FusionFlowParser#workflowFile.
    def visitWorkflowFile(self, ctx:FusionFlowParser.WorkflowFileContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FusionFlowParser#workflowDecl.
    def visitWorkflowDecl(self, ctx:FusionFlowParser.WorkflowDeclContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FusionFlowParser#workflowName.
    def visitWorkflowName(self, ctx:FusionFlowParser.WorkflowNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FusionFlowParser#workflowItem.
    def visitWorkflowItem(self, ctx:FusionFlowParser.WorkflowItemContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FusionFlowParser#constDecl.
    def visitConstDecl(self, ctx:FusionFlowParser.ConstDeclContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FusionFlowParser#conceptNameList.
    def visitConceptNameList(self, ctx:FusionFlowParser.ConceptNameListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FusionFlowParser#assertion.
    def visitAssertion(self, ctx:FusionFlowParser.AssertionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FusionFlowParser#formula.
    def visitFormula(self, ctx:FusionFlowParser.FormulaContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FusionFlowParser#comparison.
    def visitComparison(self, ctx:FusionFlowParser.ComparisonContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FusionFlowParser#comparisonOp.
    def visitComparisonOp(self, ctx:FusionFlowParser.ComparisonOpContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FusionFlowParser#term.
    def visitTerm(self, ctx:FusionFlowParser.TermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FusionFlowParser#ifExpression.
    def visitIfExpression(self, ctx:FusionFlowParser.IfExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FusionFlowParser#termList.
    def visitTermList(self, ctx:FusionFlowParser.TermListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FusionFlowParser#listLiteral.
    def visitListLiteral(self, ctx:FusionFlowParser.ListLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FusionFlowParser#atomicTerm.
    def visitAtomicTerm(self, ctx:FusionFlowParser.AtomicTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FusionFlowParser#identifier.
    def visitIdentifier(self, ctx:FusionFlowParser.IdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FusionFlowParser#conceptName.
    def visitConceptName(self, ctx:FusionFlowParser.ConceptNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FusionFlowParser#operatorName.
    def visitOperatorName(self, ctx:FusionFlowParser.OperatorNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FusionFlowParser#workflowBuiltinOperator.
    def visitWorkflowBuiltinOperator(self, ctx:FusionFlowParser.WorkflowBuiltinOperatorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FusionFlowParser#workflowOwnerOperator.
    def visitWorkflowOwnerOperator(self, ctx:FusionFlowParser.WorkflowOwnerOperatorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FusionFlowParser#stepOwnerOperator.
    def visitStepOwnerOperator(self, ctx:FusionFlowParser.StepOwnerOperatorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FusionFlowParser#dataResourceOperator.
    def visitDataResourceOperator(self, ctx:FusionFlowParser.DataResourceOperatorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FusionFlowParser#agentOwnerOperator.
    def visitAgentOwnerOperator(self, ctx:FusionFlowParser.AgentOwnerOperatorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FusionFlowParser#constantName.
    def visitConstantName(self, ctx:FusionFlowParser.ConstantNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FusionFlowParser#booleanLiteral.
    def visitBooleanLiteral(self, ctx:FusionFlowParser.BooleanLiteralContext):
        return self.visitChildren(ctx)



del FusionFlowParser