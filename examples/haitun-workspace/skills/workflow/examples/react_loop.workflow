const react_state: Artifact;
const decision: Artifact;
const observation: Artifact;
const final_answer: Artifact;

const reason_step: Step;
const action_step: Step;
const update_step: Step;
const terminal_step: TerminalStep;
const extract_answer_step: Step;

const reason_agent: Agent, Executor;
const action_agent: Agent, Executor;
const update_agent: Agent, Executor;
const terminal_agent: Agent, Executor;
const answer_agent: Agent, Executor;

workflow react_loop {
  input_workflow(react_loop) == [react_state];

  consumes(reason_step) == [react_state];
  produces(reason_step) == [decision];

  consumes(action_step) == [decision];
  produces(action_step) == [observation];

  consumes(update_step) == [react_state, decision, observation];
  produces(update_step) == [react_state];

  -- TerminalStep may omit produces; lowering creates one internal BoolArtifact.
  consumes(terminal_step) == [decision];

  -- This consumer is released only after successful loop termination.
  consumes(extract_answer_step) == [react_state];
  produces(extract_answer_step) == [final_answer];

  output_workflow(react_loop) == [final_answer];

  step_executor(reason_step) == reason_agent;
  step_executor(action_step) == action_agent;
  step_executor(update_step) == update_agent;
  step_executor(terminal_step) == terminal_agent;
  step_executor(extract_answer_step) == answer_agent;

  step_name(reason_step) == "Reason Once";
  step_instruction(reason_step) == "Read react_state and return exactly one ToolCall or Final decision. Do not execute a tool.";

  step_name(action_step) == "Act Once Or No-op";
  step_instruction(action_step) == "For ToolCall, execute exactly the selected allowed tool once and return its observation. For Final, execute no tool and return a side-effect-free final observation.";

  step_name(update_step) == "Update ReAct State";
  step_instruction(update_step) == "Append decision and observation to react_state. For Final, store the final answer; otherwise preserve everything required by the next reasoning epoch.";

  step_name(terminal_step) == "Detect Final Decision";
  step_instruction(terminal_step) == "Return exactly true for Final and exactly false for ToolCall. Produce no other output.";

  step_name(extract_answer_step) == "Extract Final Answer";
  step_instruction(extract_answer_step) == "Read the successfully terminated final react_state and return its stored final answer.";
}
