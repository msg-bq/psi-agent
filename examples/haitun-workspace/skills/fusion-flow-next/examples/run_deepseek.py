from __future__ import annotations

import argparse
import json
import os
import sys
from typing import cast

import anyio
from any_llm.api import ChatCompletion, acompletion
from examples.run_workflow import execute_workflow


def _parse_mapping(value: str, *, label: str) -> dict[str, object]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} must be a JSON object") from error
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(dict[str, object], parsed)


async def _read_inputs(value: str | None, path: str | None) -> dict[str, object]:
    if value is not None:
        return _parse_mapping(value, label="inputs")
    if path is None:
        raise ValueError("inputs or inputs file is required")
    source = await anyio.Path(path).read_text(encoding="utf-8")
    return _parse_mapping(source, label="inputs file")


async def _complete_with_deepseek(prompt: str) -> dict[str, object]:
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
                        "content": (
                            "Execute one workflow step. Return exactly one JSON object whose keys are "
                            "the requested output artifact names."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=512,
                temperature=0.0,
                response_format={"type": "json_object"},
                stream=False,
            ),
        )
    if not response.choices:
        raise RuntimeError("DeepSeek returned no choices")
    content = response.choices[0].message.content
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("DeepSeek returned no text")
    return _parse_mapping(content, label="DeepSeek response")


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Run one FusionFlow Next example with DeepSeek.")
    parser.add_argument("workflow", help="Path to a .workflow example")
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--inputs", help="JSON object containing every workflow input artifact")
    inputs.add_argument("--inputs-file", help="UTF-8 JSON file containing every workflow input artifact")
    args = parser.parse_args()
    source = await anyio.Path(args.workflow).read_text(encoding="utf-8")
    result = await execute_workflow(
        source,
        inputs=await _read_inputs(args.inputs, args.inputs_file),
        complete=_complete_with_deepseek,
    )
    sys.stdout.write(f"{json.dumps(result, ensure_ascii=False, indent=2)}\n")


if __name__ == "__main__":
    anyio.run(_main)
