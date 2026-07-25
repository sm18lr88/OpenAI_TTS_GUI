from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_python_contracts.py"
RULES = ROOT / "quality" / "python" / "rules.json"


def check(source: str, tmp_path: Path) -> list[dict[str, str | int]]:
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
    return json.loads(result.stdout)["findings"]


def rule_ids(source: str, tmp_path: Path) -> set[str]:
    return {str(finding["rule_id"]) for finding in check(source, tmp_path)}


def rule_count(source: str, tmp_path: Path, rule: str) -> int:
    return sum(finding["rule_id"] == rule for finding in check(source, tmp_path))


@pytest.mark.parametrize(
    "source",
    [
        "from typing import Any\ndef f(*args: Any) -> None: pass\n",
        "def f(**kwargs: object) -> None: pass\n",
        "from typing import Any\ntype Alias = list[Any]\n",
        "from typing import Any, cast\ndef f(value=cast(Any, 1)):\n    cast = int\n",
        "from typing import Any, cast\nvalue = lambda item=cast(Any, 1): item\n",
    ],
)
def test_scope_checker_visits_pep695_and_all_default_annotation_forms(
    tmp_path: Path, source: str
) -> None:
    # Given: prohibited annotation constructs in forms the active visitor previously skipped.
    # When: the checker scans the source.
    # Then: every form remains visible to the applicable rule.
    assert rule_ids(source, tmp_path) & {"ANY001", "OBJ001", "CAST001"}


@pytest.mark.parametrize(
    ("source", "rule"),
    [
        ("from typing import Any\ntype Alias[T: list[Any]] = T\n", "ANY001"),
        ("type Alias[T: list[object]] = T\n", "OBJ001"),
        ("from typing import Any\ntype Alias[T = list[Any]] = T\n", "ANY001"),
        ("type Alias[T = list[object]] = T\n", "OBJ001"),
    ],
)
def test_scope_checker_inspects_pep695_nested_bounds_and_defaults(
    tmp_path: Path, source: str, rule: str
) -> None:
    # Given: a nested prohibited annotation in a PEP695 bound or default.
    # When: the checker scans the alias.
    # Then: the matching annotation rule is emitted.
    assert rule in rule_ids(source, tmp_path)


@pytest.mark.parametrize(
    "source",
    [
        "from typing import Any\nfor Any in values:\n    value: Any\n",
        "from typing import Any\nwith resource() as Any:\n    value: Any\n",
        "from typing import Any\ntry:\n    pass\nexcept Exception as Any:\n    value: Any\n",
        "from typing import Any\ndef f():\n    value: Any\n    Any = int\n",
        "from typing import Any\ndef f():\n    global Any\n    Any = int\n    value: Any\n",
        (
            "from typing import Any\ndef outer():\n    Any = int\n"
            "    def inner():\n        nonlocal Any\n        Any = str\n        value: Any\n"
        ),
        "from typing import Any\nvalues = [cast(Any, 1) for Any in items]\n",
        "from typing import Any\nmatch value:\n    case Any:\n        result: Any\n",
        "from typing import Any\ntype Alias[Any] = list[Any]\n",
        "from typing import Any\ntype Alias[Any: list[Any] = list[Any]] = Any\n",
        "type Alias[object: list[object] = list[object]] = object\n",
        "from typing import Any\nclass Box[Any: list[Any] = list[Any]]: pass\n",
        "class Box[object: list[object] = list[object]]: pass\n",
        "from typing import Any\ndef f[Any](value: Any) -> Any: return value\n",
    ],
)
def test_scope_checker_respects_compile_time_and_nested_bindings(
    tmp_path: Path, source: str
) -> None:
    # Given: a binding that shadows a prohibited import in a Python lexical scope.
    # When: the checker resolves the later use.
    # Then: the shadowed spelling is not reported as typing.Any.
    assert "ANY001" not in rule_ids(source, tmp_path)


@pytest.mark.parametrize(
    ("source", "rule"),
    [
        ("from typing import Any\ntype Alias[T: list[Any]] = T\n", "ANY001"),
        ("type Alias[T: list[object]] = T\n", "OBJ001"),
        ("from typing import Any\nclass Box[T: list[Any]]: pass\n", "ANY001"),
        ("class Box[T: list[object]]: pass\n", "OBJ001"),
    ],
)
def test_scope_checker_retains_outer_type_parameter_annotations(
    tmp_path: Path, source: str, rule: str
) -> None:
    assert rule in rule_ids(source, tmp_path)


@pytest.mark.parametrize(
    ("name", "prefix", "rule"),
    [
        ("Any", "from typing import Any\n", "ANY001"),
        ("object", "", "OBJ001"),
    ],
)
def test_scope_checker_resolves_alias_type_parameters_before_and_after_declaration(
    tmp_path: Path, name: str, prefix: str, rule: str
) -> None:
    # Given: prior and forward type parameters that shadow a prohibited outer spelling.
    source = (
        prefix
        + f"type Prior[{name}, T: list[{name}] = list[{name}]] = tuple[T, {name}]\n"
        + (
            f"type Forward[T: list[{name}] = list[{name}], "
            f"{name}: {name} = {name}] = tuple[T, {name}]\n"
        )
        + f"type Outer[T: list[{name}] = list[{name}]] = T\n"
    )

    # When: the checker inspects all alias bounds and defaults.
    # Then: only the unrelated outer alias emits its two real findings.
    assert rule_count(source, tmp_path, rule) == 2


@pytest.mark.parametrize(
    ("name", "prefix", "rule"),
    [
        ("Any", "from typing import Any\n", "ANY001"),
        ("object", "", "OBJ001"),
    ],
)
def test_scope_checker_resolves_class_type_parameters_before_and_after_declaration(
    tmp_path: Path, name: str, prefix: str, rule: str
) -> None:
    # Given: generic classes whose prior and forward parameters shadow a prohibited spelling.
    source = (
        prefix
        + f"class Prior[{name}, T: list[{name}] = list[{name}]]:\n    value: tuple[T, {name}]\n"
        + (
            f"class Forward[T: list[{name}] = list[{name}], {name}: {name} = {name}]:\n"
            f"    value: tuple[T, {name}]\n"
        )
        + f"class Outer[T: list[{name}] = list[{name}]]:\n    value: T\n"
    )

    # When: the checker inspects all class bounds and defaults.
    # Then: only the unrelated outer class emits its two real findings.
    assert rule_count(source, tmp_path, rule) == 2


@pytest.mark.parametrize(
    ("name", "prefix", "rule"),
    [
        ("Any", "from typing import Any\n", "ANY001"),
        ("object", "", "OBJ001"),
    ],
)
def test_scope_checker_resolves_function_type_parameters_before_and_after_declaration(
    tmp_path: Path, name: str, prefix: str, rule: str
) -> None:
    # Given: generic functions whose prior and forward parameters shadow a prohibited spelling.
    source = (
        prefix
        + (
            f"def prior[{name}, T: list[{name}] = list[{name}]]"
            f"(value: tuple[T, {name}]) -> {name}:\n    return value\n"
        )
        + (
            f"def forward[T: list[{name}] = list[{name}], {name}: {name} = {name}]"
            f"(value: tuple[T, {name}]) -> {name}:\n    return value\n"
        )
        + f"def outer[T: list[{name}] = list[{name}]](value: T) -> T:\n    return value\n"
    )

    # When: the checker inspects all function bounds, defaults, and annotations.
    # Then: only the unrelated outer function emits its two real findings.
    assert rule_count(source, tmp_path, rule) == 2


def test_var_chain_traverses_every_branch_after_single_outer_finding(tmp_path: Path) -> None:
    # Given: a canonical equality chain with annotations in each body and the final else.
    source = (
        "from typing import Any\n"
        "if value == 1:\n    first: Any\n"
        "elif value == 2:\n    second: Any\n"
        "elif value == 3:\n    third: Any\n"
        "else:\n    fourth: Any\n"
    )

    # When: the checker scans the complete if/elif/else tree.
    findings = check(source, tmp_path)

    # Then: VAR001 is emitted once while all branches still contribute their findings.
    assert [finding["rule_id"] for finding in findings].count("VAR001") == 1
    assert [finding["rule_id"] for finding in findings].count("ANY001") == 4
