const engineering_state: Artifact;
const discovered_work: Artifact;
const candidate_change: Artifact;
const verification: Artifact;
const done: BoolArtifact;

const inspect_step: Step;
const engineer_step: Step;
const verify_step: Step;
const advance_step: Step;
const terminal_step: TerminalStep;

const inspect_agent: Agent, Executor;
const engineer_agent: Agent, Executor;
const verify_agent: Agent, Executor;
const advance_agent: Agent, Executor;
const terminal_agent: Agent, Executor;

workflow loop_engineering {
  input_workflow(loop_engineering) == [engineering_state];

  consumes(inspect_step) == [engineering_state];
  produces(inspect_step) == [discovered_work];

  consumes(engineer_step) == [engineering_state, discovered_work];
  produces(engineer_step) == [candidate_change];

  consumes(verify_step) == [engineering_state, discovered_work, candidate_change];
  produces(verify_step) == [verification];

  consumes(advance_step) == [engineering_state, discovered_work, candidate_change, verification];
  produces(advance_step) == [engineering_state];

  consumes(terminal_step) == [verification];
  produces(terminal_step) == [done];

  output_workflow(loop_engineering) == [engineering_state];

  step_executor(inspect_step) == inspect_agent;
  step_executor(engineer_step) == engineer_agent;
  step_executor(verify_step) == verify_agent;
  step_executor(advance_step) == advance_agent;
  step_executor(terminal_step) == terminal_agent;

  step_name(inspect_step) == "Inspect and Plan";
  step_instruction(inspect_step) == "Inspect engineering_state and return unresolved work, evidence, priorities, and acceptance criteria.";

  step_name(engineer_step) == "Engineer Candidate";
  step_instruction(engineer_step) == "Use engineering_state and discovered_work to produce one isolated candidate_change that can be verified before commit.";

  step_name(verify_step) == "Verify Candidate";
  step_instruction(verify_step) == "Verify candidate_change against the baseline and acceptance criteria. Return one verdict, test evidence, regressions, and remaining work.";

  step_name(advance_step) == "Advance Engineering State";
  step_instruction(advance_step) == "Produce the next engineering_state. Incorporate only verified progress and preserve evidence and remaining work for the next epoch.";

  step_name(terminal_step) == "Check Completion";
  step_instruction(terminal_step) == "Return exactly true iff verification says every required criterion passed; otherwise return exactly false.";
}
