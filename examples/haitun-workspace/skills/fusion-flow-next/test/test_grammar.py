from __future__ import annotations

import hashlib
import importlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRAMMAR = ROOT / "grammar" / "FusionFlow.g4"
GENERATED = ROOT / "fusion_flow_next" / "generated"


def test_preset_operators_document_signatures() -> None:
    grammar = GRAMMAR.read_text(encoding="utf-8")
    preset_operators = re.findall(
        r"^\s*(?::|\|)\s*'([a-z][a-z0-9_]*)'\s*$",
        grammar,
        re.MULTILINE,
    )
    signatures = re.findall(
        r"^\s*\*\s+([a-z][a-z0-9_]*)\(([^)]*)\)\s*->\s*[A-Z][A-Za-z0-9_]*\s+\[arity\s+(\d+)\]\s*$",
        grammar,
        re.MULTILINE,
    )

    assert sorted(name for name, _, _ in signatures) == sorted(set(preset_operators))
    for operator, parameters, arity in signatures:
        parameter_types = [item.strip() for item in parameters.split(",") if item.strip()]
        assert all(re.fullmatch(r"[A-Z][A-Za-z0-9_]*", item) for item in parameter_types), operator
        assert len(parameter_types) == int(arity), operator


def test_generated_parser_matches_grammar_checksum() -> None:
    expected = hashlib.sha256(GRAMMAR.read_bytes()).hexdigest()
    actual = (GENERATED / "FusionFlow.sha256").read_text(encoding="ascii").strip()

    assert actual == expected


def test_generated_parser_imports() -> None:
    importlib.import_module("fusion_flow_next.generated.FusionFlowLexer")
    importlib.import_module("fusion_flow_next.generated.FusionFlowParser")
