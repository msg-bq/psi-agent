from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from os import PathLike
from os.path import isabs
from typing import Literal, cast

from fusion_flow_next import (
    Assertion,
    CompoundTerm,
    Concept,
    Constant,
    Operator,
    ParseContext,
    WorkflowGraphCompilation,
    WorkflowGraphCompiler,
    parse_workflow,
)
from fusion_flow_next.execution import AgentConfig, AgentHandle, RunContext, SessionRunner, flow
from fusion_flow_next.execution import run as run_execution

from psi_agent.workflow_execution import StepDispatcher, execute_plan, generate_plan
from psi_agent.workflow_graph import ProducesEdge, StepNode, WorkflowGraph

type InstructionResolver = Callable[[str], Awaitable[str]]
type PathResolver = Callable[[str], Awaitable[str]]
type HumanInstructionPreparer = Callable[[str], Awaitable[str]]
type HumanRequester = Callable[[str], Awaitable[object]]
type ExecutorKind = Literal["Agent", "Human", "Program"]


@dataclass(frozen=True, slots=True)
class CompiledWorkflow:
    graph: WorkflowGraph
    executor_kinds: Mapping[str, ExecutorKind]
    program_paths: Mapping[str, str]
    agent_systems: Mapping[str, str]


_CONCEPT_NAMES = (
    "Agent",
    "Artifact",
    "Bool",
    "ComplexNumber",
    "Human",
    "Instruction",
    "Path",
    "Program",
    "Step",
    "StepName",
    "Workflow",
)
_OPERATOR_NAMES = (
    "agent_system",
    "consumes",
    "input_workflow",
    "max_concurrency",
    "output_workflow",
    "produces",
    "program_path",
    "step_executor",
    "step_instruction",
    "step_name",
)
_EXECUTOR_CONFIGURATION_OPERATORS = frozenset({"agent_system", "program_path"})
_DEFAULT_AGENT_SYSTEM = "Execute the workflow step using its instruction and artifact context."


def _typed_constant(value: object, concept_name: str, context: str) -> Constant:
    if not isinstance(value, Constant) or not value.symbol:
        raise ValueError(f"{context} must be a non-empty constant")
    concepts = {concept.name for concept in value.belong_concepts}
    if concept_name not in concepts:
        raise ValueError(f"{context} must belong to {concept_name}")
    return value


def _extract_executor_configuration(
    assertions: tuple[Assertion, ...],
) -> tuple[dict[str, str], dict[str, str], tuple[Assertion, ...]]:
    program_paths: dict[str, str] = {}
    agent_systems: dict[str, str] = {}
    residual: list[Assertion] = []

    for assertion in assertions:
        candidates = tuple(
            (term, value)
            for term, value in (
                (assertion.lhs, assertion.rhs),
                (assertion.rhs, assertion.lhs),
            )
            if isinstance(term, CompoundTerm) and term.operator.name in _EXECUTOR_CONFIGURATION_OPERATORS
        )
        if not candidates:
            residual.append(assertion)
            continue
        if len(candidates) != 1:
            raise ValueError("one equality cannot configure multiple executors")

        call, value = candidates[0]
        if len(call.arguments) != 1:
            raise ValueError(f"{call.operator.name} expects 1 argument, got {len(call.arguments)}")

        if call.operator.name == "program_path":
            executor = _typed_constant(call.arguments[0], "Program", "program_path argument")
            path = _typed_constant(value, "Path", "program_path value")
            target = program_paths
            configured_value = path.symbol
        else:
            executor = _typed_constant(call.arguments[0], "Agent", "agent_system argument")
            system = _typed_constant(value, "Instruction", "agent_system value")
            target = agent_systems
            configured_value = system.symbol

        if executor.symbol in target:
            raise ValueError(f"duplicate {call.operator.name} for {executor.symbol!r}")
        target[executor.symbol] = configured_value

    return program_paths, agent_systems, tuple(residual)


def compile_workflow(source: str) -> CompiledWorkflow:
    """Parse and compile one workflow into an executable graph."""

    concepts = {name: Concept(name) for name in _CONCEPT_NAMES}
    operators = {name: Operator(name) for name in _OPERATOR_NAMES}
    operators["step_instruction"] = Operator(
        name="step_instruction",
        input_concepts=(concepts["Step"],),
        output_concept=concepts["Instruction"],
    )
    operators["program_path"] = Operator(
        name="program_path",
        input_concepts=(concepts["Program"],),
        output_concept=concepts["Path"],
    )
    operators["agent_system"] = Operator(
        name="agent_system",
        input_concepts=(concepts["Agent"],),
        output_concept=concepts["Instruction"],
    )
    context = ParseContext(
        concepts=concepts,
        operators=operators,
    )
    parsed = parse_workflow(source, context=context)
    if parsed.core_ir is None:
        details = "; ".join(
            (
                diagnostic.message
                if diagnostic.span is None
                else f"{diagnostic.span.start.line}:{diagnostic.span.start.column}: {diagnostic.message}"
            )
            for diagnostic in parsed.diagnostics
        )
        raise ValueError(f"workflow parse failed: {details}")

    compiled = WorkflowGraphCompiler().compile(parsed.core_ir)
    if not isinstance(compiled, tuple):
        raise TypeError("workflow graph compiler returned an unexpected result")
    compilations = cast(tuple[WorkflowGraphCompilation, ...], compiled)
    if len(compilations) != 1:
        raise ValueError("workflow runner expects exactly one workflow")
    compilation = compilations[0]
    program_paths, agent_systems, residual = _extract_executor_configuration(compilation.residual_assertions)
    if residual:
        raise ValueError("workflow contains assertions that the graph compiler cannot execute")
    executor_kinds: dict[str, ExecutorKind] = {}
    for constant in parsed.core_ir.constants:
        matches = {concept.name for concept in constant.belong_concepts} & {"Agent", "Human", "Program"}
        if len(matches) == 1:
            executor_kinds[constant.symbol] = cast(ExecutorKind, matches.pop())
    for step in compilation.graph.steps:
        executor_kinds.setdefault(step.executor_id, "Agent")
        if executor_kinds[step.executor_id] == "Program" and step.executor_id not in program_paths:
            raise ValueError(f"Program executor {step.executor_id!r} has no program_path")
    return CompiledWorkflow(
        graph=compilation.graph,
        executor_kinds=executor_kinds,
        program_paths=program_paths,
        agent_systems=agent_systems,
    )


async def _build_agent_handles(
    compiled: CompiledWorkflow,
    resolve_instruction: InstructionResolver | None,
) -> dict[str, AgentHandle]:
    handles: dict[str, AgentHandle] = {}
    agent_ids = {
        step.executor_id for step in compiled.graph.steps if compiled.executor_kinds[step.executor_id] == "Agent"
    }
    for agent_id in sorted(agent_ids):
        system_reference = compiled.agent_systems.get(agent_id)
        if system_reference is None:
            system = _DEFAULT_AGENT_SYSTEM
        else:
            if resolve_instruction is None:
                raise ValueError(f"Agent executor {agent_id!r} has agent_system but no instruction resolver")
            system = await resolve_instruction(system_reference)
            if not isinstance(system, str) or not system.strip():
                raise ValueError(f"agent_system for {agent_id!r} resolved to no text")
        handles[agent_id] = flow.agent(AgentConfig(name=agent_id, system=system))
    return handles


async def _build_program_paths(
    compiled: CompiledWorkflow,
    resolve_path: PathResolver | None,
) -> dict[str, str]:
    paths: dict[str, str] = {}
    program_ids = {
        step.executor_id for step in compiled.graph.steps if compiled.executor_kinds[step.executor_id] == "Program"
    }
    for program_id in sorted(program_ids):
        path_reference = compiled.program_paths[program_id]
        if isabs(path_reference) or path_reference.startswith("./"):
            executable_path = path_reference
        else:
            if resolve_path is None:
                raise ValueError(f"Program executor {program_id!r} has a path identity but no path resolver")
            executable_path = await resolve_path(path_reference)
            if not isinstance(executable_path, str) or not executable_path.strip():
                raise ValueError(f"program_path for {program_id!r} resolved to no path")
        paths[program_id] = executable_path
    return paths


def _agent_context(inputs: Mapping[str, object]) -> dict[str, str]:
    return {
        name: value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        for name, value in inputs.items()
    }


def _build_dispatch(
    compiled: CompiledWorkflow,
    agent_handles: Mapping[str, AgentHandle],
    program_paths: Mapping[str, str],
    work_dir: str | PathLike[str] | None,
    prepare_human_instruction: HumanInstructionPreparer | None,
    request_human: HumanRequester | None,
) -> StepDispatcher:
    graph = compiled.graph
    outputs_by_step: dict[str, list[str]] = {step.step_id: [] for step in graph.steps}
    for edge in graph.edges:
        if isinstance(edge, ProducesEdge):
            outputs_by_step[edge.step_id].append(edge.artifact_id)

    async def dispatch(step: StepNode, inputs: Mapping[str, object]) -> Mapping[str, object]:
        if step.instruction_id is None:
            raise ValueError(f"step {step.step_id!r} has no step_instruction")
        output_ids = outputs_by_step[step.step_id]
        if len(output_ids) != 1:
            raise ValueError(f"step {step.step_id!r} must produce exactly one artifact")
        instruction = step.instruction_id
        if compiled.executor_kinds[step.executor_id] == "Human":
            if prepare_human_instruction is None or request_human is None:
                raise ValueError(
                    f"step {step.step_id!r} requires prepare_human_instruction and request_human callbacks"
                )
            preparation_prompt = (
                "Prepare this workflow step for a human.\n"
                f"Step: {step.step_id}\n"
                f"Instruction or reference: {instruction}\n"
                f"Inputs: {json.dumps(dict(inputs), ensure_ascii=False, sort_keys=True, default=str)}\n"
                "Produce concise, readable guidance. Decide whether referenced resources need inspection "
                "using your available tools and normal approval flow. Do not invent inaccessible contents."
            )
            prepared_instruction = await prepare_human_instruction(preparation_prompt)
            if not prepared_instruction.strip():
                raise ValueError(f"step {step.step_id!r} human instruction preparation returned no text")
            return {output_ids[0]: await request_human(prepared_instruction)}
        if compiled.executor_kinds[step.executor_id] == "Agent":
            result = await flow.session(
                agent_handles[step.executor_id],
                instruction,
                _agent_context(inputs),
                binding_name=step.step_id,
            )
            return {output_ids[0]: result}

        program_path = program_paths[step.executor_id]
        payload = json.dumps(
            {"instruction": instruction, "inputs": dict(inputs)},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        result = await flow.exec(
            step.executor_id,
            (program_path,),
            stdin=f"{payload}\n",
            cwd=work_dir,
            binding_name=step.step_id,
        )
        return {output_ids[0]: result.stdout}

    return dispatch


async def execute_workflow(
    source: str,
    *,
    inputs: Mapping[str, object],
    runner: SessionRunner | None = None,
    resolve_instruction: InstructionResolver | None = None,
    resolve_path: PathResolver | None = None,
    prepare_human_instruction: HumanInstructionPreparer | None = None,
    request_human: HumanRequester | None = None,
    runs_dir: str | PathLike[str] = "runs",
    work_dir: str | PathLike[str] | None = None,
) -> dict[str, object]:
    """Execute one workflow through the FusionFlow session and subprocess runtime."""

    compiled = compile_workflow(source)
    graph = compiled.graph
    program_paths = await _build_program_paths(compiled, resolve_path)
    if work_dir is None and any(not isabs(path) for path in program_paths.values()):
        raise ValueError("relative program_path requires an explicit work_dir")
    plan = generate_plan(graph)
    agent_handles = await _build_agent_handles(compiled, resolve_instruction)
    if agent_handles and runner is None:
        raise ValueError("Agent workflow requires an injected session runner")
    dispatch = _build_dispatch(
        compiled,
        agent_handles,
        program_paths,
        work_dir,
        prepare_human_instruction,
        request_human,
    )

    outputs: dict[str, object] | None = None

    async def program(_: RunContext) -> None:
        nonlocal outputs
        outputs = await execute_plan(
            plan,
            graph,
            inputs=inputs,
            dispatch=dispatch,
        )

    await run_execution(
        program,
        runs_dir=runs_dir,
        runner=runner,
        throw_on_error=True,
    )
    if outputs is None:
        raise RuntimeError("workflow execution completed without outputs")
    return outputs
