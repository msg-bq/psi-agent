-- Standalone syntax catalog for all 23 preset workflow operators.
-- Concepts and operator signatures come from the external catalog; this file
-- declares only the concrete identities used by this workflow.

const report_flow:Workflow;
const fetch_step:Step;
const analyze_step:Step;
const review_step:Step;
const format_step:Step;
const source:Artifact;
const report:Artifact;
const file_a:Artifact;
const file_b:Artifact;
const file:Artifact;
const files:List;
const cpu_millicore:Resource;
const writer_agent:Agent;
const alice:Human;
const formatter_program:Program;
const claude_sonnet:Model;
const claude_cli:Engine;
const internal_llm_api:ApiBase;
const web_search:Tool;
const fetch_source:StepName;
const download_source:Instruction;

workflow report_pipeline {
    -- Workflow owner operators
    input_workflow(report_flow, source) = true;
    input_workflow_multi(report_flow) = [source, file_a];
    output_workflow(report_flow, report) = true;
    output_workflow_multi(report_flow) = [report, file_b];
    max_concurrency(report_flow) = 4;
    workflow_timeout(report_flow) = 240 + 60;

    -- Step owner operators
    step_name(fetch_step) = fetch_source;
    step_instruction(fetch_step) = download_source;
    step_executor(fetch_step) = writer_agent;
    step_executor(format_step) = formatter_program;
    step_timeout(fetch_step) = 60;
    max_attempts(fetch_step) = 3;

    -- Data, loop, and resource operators
    files = [file_a, file_b];
    consumes(fetch_step, source) = true;
    consumes_multi(format_step) = [source, report];
    produces(fetch_step, report) = true;
    produces_multi(format_step) = [file_a, file_b];
    foreach_item(analyze_step, files) = file;
    consumes(analyze_step, file) = true;
    resource_requirement(analyze_step, cpu_millicore) = 2000;

    -- Agent owner operators
    agent_config(
        writer_agent,
        claude_sonnet,
        claude_cli,
        internal_llm_api
    ) = true;
    allowed_tool(writer_agent, web_search) = true;
    max_output_tokens(writer_agent) = 4096;
    temperature(writer_agent) = 0.7;
    reasoning_effort(writer_agent) = high;
    max_turns(writer_agent) = 8;

    -- if(condition, then_term, else_term) is a three-argument value expression.
    step_executor(review_step) = if(
        !(reasoning_effort(writer_agent) != high)
            AND (
                max_attempts(fetch_step) >= 2
                OR step_timeout(fetch_step) > 30
            ),
        writer_agent,
        alice
    );
}
