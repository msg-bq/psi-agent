from __future__ import annotations

import importlib.util
import os
import sys
from types import SimpleNamespace
from typing import Any, cast

import anyio
import pytest

_SKILL_DIR = os.path.dirname(os.path.dirname(__file__))
_RUNNER_PATH = os.path.join(_SKILL_DIR, "examples", "run_deepseek.py")


def _load_module(name: str, path: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return cast(Any, module)


run_deepseek = _load_module("fusion_flow_next_deepseek_runner", _RUNNER_PATH)


def test_parse_mapping_requires_json_object() -> None:
    assert run_deepseek._parse_mapping('{"request": "hello"}', label="inputs") == {"request": "hello"}

    with pytest.raises(ValueError, match="inputs must be a JSON object"):
        run_deepseek._parse_mapping('["hello"]', label="inputs")


@pytest.mark.anyio
async def test_read_inputs_from_file(tmp_path: Any) -> None:
    inputs_path = os.path.join(str(tmp_path), "inputs.json")
    await anyio.Path(inputs_path).write_text('{"request": "hello"}', encoding="utf-8")

    assert await run_deepseek._read_inputs(None, inputs_path) == {"request": "hello"}


@pytest.mark.anyio
async def test_deepseek_completion_returns_named_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[dict[str, object]] = []

    async def fake_acompletion(**kwargs: object) -> SimpleNamespace:
        requests.append(dict(kwargs))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"draft": "short answer"}'))])

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(run_deepseek, "acompletion", fake_acompletion)

    result = await run_deepseek._complete_with_deepseek('Outputs: ["draft"]')

    assert result == {"draft": "short answer"}
    assert requests[0]["response_format"] == {"type": "json_object"}
