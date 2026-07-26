const single_step: Workflow;
const answer_step: Step;
const answer_name: StepName;
const deepseek_agent: Agent;
const request: Artifact;
const result: Artifact;

workflow single_step {
    input_workflow(single_step, request) == True;
    output_workflow(single_step, result) == True;
    step_name(answer_step) == answer_name;
    step_instruction(answer_step) == "./instructions/answer-the-request.md";
    step_executor(answer_step) == deepseek_agent;
    consumes(answer_step, request) == True;
    produces(answer_step, result) == True;
}
