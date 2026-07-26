from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Literal, cast

import anyio
from any_llm.api import ChatCompletion, acompletion
from fusion_flow_next import (
    Concept,
    Operator,
    ParseContext,
    WorkflowGraphCompilation,
    WorkflowGraphCompiler,
    parse_workflow,
)

from psi_agent.workflow_execution import StepDispatcher, execute_plan, generate_plan
from psi_agent.workflow_graph import ProducesEdge, StepNode, WorkflowGraph

type Completion = Callable[[str], Awaitable[str]]
type ExecutorKind = Literal["Agent", "Human", "Program"]


@dataclass(frozen=True, slots=True)
class CompiledWorkflow:
    graph: WorkflowGraph
    executor_kinds: Mapping[str, ExecutorKind]


_CONCEPT_NAMES = (
    "Agent",
    "Artifact",
    "Bool",
    "ComplexNumber",
    "Human",
    "Instruction",
    "Program",
    "Step",
    "StepName",
    "Workflow",
)
_OPERATOR_NAMES = (
    "consumes",
    "input_workflow",
    "max_concurrency",
    "output_workflow",
    "produces",
    "step_executor",
    "step_instruction",
    "step_name",
)


def compile_workflow(source: str) -> CompiledWorkflow:
    """Parse and compile one example workflow into an executable graph."""

    concepts = {name: Concept(name) for name in _CONCEPT_NAMES}
    operators = {name: Operator(name) for name in _OPERATOR_NAMES}
    operators["step_instruction"] = Operator(
        name="step_instruction",
        input_concepts=(concepts["Step"],),
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
        raise ValueError("example runner expects exactly one workflow")
    compilation = compilations[0]
    if compilation.residual_assertions:
        raise ValueError("example contains assertions that the graph compiler cannot execute")
    executor_kinds: dict[str, ExecutorKind] = {}
    for constant in parsed.core_ir.constants:
        matches = {concept.name for concept in constant.belong_concepts} & {"Agent", "Human", "Program"}
        if len(matches) == 1:
            executor_kinds[constant.symbol] = cast(ExecutorKind, matches.pop())
    return CompiledWorkflow(graph=compilation.graph, executor_kinds=executor_kinds)


async def _read_human_instruction(workflow_path: str, instruction_path: str) -> str:
    if os.path.splitext(workflow_path)[1] != ".workflow":
        raise ValueError("a .workflow file path is required to resolve a human instruction")
    if (
        os.path.isabs(instruction_path)
        or os.path.splitdrive(instruction_path)[0]
        or instruction_path.startswith(("/", "\\"))
        or (len(instruction_path) > 1 and instruction_path[1] == ":")
    ):
        raise ValueError("human instruction path must be relative to the workflow")
    if not instruction_path.startswith("./"):
        raise ValueError("human instruction path must start with './'")

    relative_path = instruction_path[2:]
    if (
        not relative_path
        or os.path.isabs(relative_path)
        or os.path.splitdrive(relative_path)[0]
        or relative_path.startswith(("//", "\\\\"))
        or (len(relative_path) > 1 and relative_path[1] == ":")
    ):
        raise ValueError("human instruction path must be relative to the workflow")
    if ".." in relative_path.replace("\\", "/").split("/"):
        raise ValueError("human instruction path must not contain '..' segments")

    base_path = str(await anyio.Path(os.path.dirname(workflow_path)).resolve())
    target_path = str(await anyio.Path(os.path.join(base_path, relative_path)).resolve())
    try:
        common_path = os.path.commonpath((base_path, target_path))
    except ValueError:
        raise ValueError("human instruction file escapes the workflow directory") from None
    if os.path.normcase(common_path) != os.path.normcase(base_path):
        raise ValueError("human instruction file escapes the workflow directory")

    path = anyio.Path(target_path)
    if not await path.exists():
        raise ValueError(f"human instruction file does not exist: {instruction_path}")
    if not await path.is_file():
        raise ValueError(f"human instruction path must reference a regular file: {instruction_path}")
    try:
        instruction = await path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"human instruction file must be valid UTF-8: {instruction_path}") from error
    if not instruction.strip():
        raise ValueError(f"human instruction file must not be empty: {instruction_path}")
    return instruction


def _build_dispatch(
    compiled: CompiledWorkflow,
    complete: Completion,
    workflow_path: str,
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
            raise ValueError(f"example step {step.step_id!r} must produce exactly one artifact")
        instruction = step.instruction_id
        if instruction.startswith("./") and compiled.executor_kinds[step.executor_id] == "Human":
            instruction = await _read_human_instruction(workflow_path, instruction)
        prompt = (
            f"Instruction: {instruction}\n"
            f"Inputs: {json.dumps(dict(inputs), ensure_ascii=False, sort_keys=True, default=str)}\n"
            "Return only the result for this workflow step."
        )
        return {output_ids[0]: await complete(prompt)}

    return dispatch


async def execute_workflow(
    source: str,
    *,
    workflow_path: str,
    request: str,
    complete: Completion,
) -> dict[str, object]:
    """Execute one bundled example with an injected text completion function."""

    compiled = compile_workflow(source)
    graph = compiled.graph
    return await execute_plan(
        generate_plan(graph),
        graph,
        inputs={"request": request},
        dispatch=_build_dispatch(compiled, complete, workflow_path),
    )


async def _complete_with_deepseek(prompt: str) -> str:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is required")
    with anyio.fail_after(120):
        response = cast(
            ChatCompletion,
            await acompletion(
                provider="deepseek",
                model="deepseek-v4-flash",
                api_key=api_key,
                api_base="https://api.deepseek.com/v1",
                messages=[
                    {
                        "role": "system",
                        "content": "Execute one workflow step. Return only its concise result.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=512,
                temperature=0.0,
                stream=False,
            ),
        )
    if not response.choices:
        raise RuntimeError("DeepSeek returned no choices")
    content = response.choices[0].message.content
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("DeepSeek returned no text")
    return content.strip()


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Run one FusionFlow Next example with DeepSeek.")
    parser.add_argument("workflow", help="Path to a .workflow example")
    parser.add_argument("request", help="Value for the example's request artifact")
    args = parser.parse_args()
    source = await anyio.Path(args.workflow).read_text(encoding="utf-8")
    result = await execute_workflow(
        source,
        workflow_path=args.workflow,
        request=args.request,
        complete=_complete_with_deepseek,
    )
    sys.stdout.write(f"{json.dumps(result, ensure_ascii=False, indent=2)}\n")


if __name__ == "__main__":
    anyio.run(_main)
