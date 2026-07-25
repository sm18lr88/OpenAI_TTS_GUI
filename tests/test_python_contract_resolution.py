from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_python_contracts.py"
RULES = ROOT / "quality" / "python" / "rules.json"


def run(source: str, tmp_path: Path) -> set[str]:
    module = tmp_path / "sample.py"
    boundaries = tmp_path / "boundaries.json"
    module.write_text(source, encoding="utf-8")
    boundaries.write_text('{"version": 1, "entries": []}', encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(module),
            "--rules",
            str(RULES),
            "--boundaries",
            str(boundaries),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    return {finding["rule_id"] for finding in json.loads(result.stdout)["findings"]}


@pytest.mark.parametrize(
    ("source", "rule"),
    [
        ("import typing as t\nx: t.Any\n", "ANY001"),
        ("from typing import cast as c\nx = c(int, 1)\n", "CAST001"),
        ("import builtins as b\nx: list[b.object]\n", "OBJ001"),
        ("from typing import TypeAlias\nAlias: TypeAlias = list[object]\n", "OBJ001"),
        ("import builtins as b\nraise b.ValueError\n", "ERR001"),
        ("try:\n    pass\nexcept (ValueError, Exception):\n    pass\n", "CATCH001"),
        (
            "import contextlib\nwith contextlib.suppress(ValueError, Exception):\n    pass\n",
            "CATCH001",
        ),
        ("import dataclasses\n@dataclasses.dataclass\nclass Mutable: pass\n", "DATA001"),
    ],
)
def test_contract_rules_resolve_qualified_and_structural_forms(
    tmp_path: Path, source: str, rule: str
) -> None:
    # Given: a resolved stdlib spelling of a prohibited construct.
    # When: the contract checker scans it.
    # Then: the matching rule is reported.
    assert rule in run(source, tmp_path)


@pytest.mark.parametrize(
    "source",
    [
        (
            "from contextlib import suppress\nsuppress = lambda error: error\n"
            "with suppress(Exception):\n    pass\n"
        ),
        "from typing import Any\ndef f(Any: type[int]) -> None:\n    value: Any\n",
        "from builtins import object\ndef f(object: type[int]) -> None:\n    value: object\n",
        (
            "from dataclasses import dataclass\ndef f():\n    def dataclass(value):\n"
            "        return value\n    @dataclass\n    class Frozen:\n        pass\n"
        ),
    ],
)
def test_contract_rules_respect_lexical_shadowing(tmp_path: Path, source: str) -> None:
    # Given: a binding which shadows an imported or builtin symbol before its use.
    # When: the checker scans the lexical scope.
    # Then: no unrelated rule is reported.
    assert run(source, tmp_path) == set()
