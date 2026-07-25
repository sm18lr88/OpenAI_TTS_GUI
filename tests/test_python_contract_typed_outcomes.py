from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_python_contract_boundary_exemptions import check

ENTRY = {
    "path": "sample.py",
    "symbol": "sample.load",
    "kind": "catch_boundary",
    "rationale": "typed result",
    "obligation": "typed_outcome",
}


def outcome_source(return_type: str, handler_return: str) -> str:
    return (
        "from dataclasses import dataclass\n"
        "@dataclass(frozen=True, slots=True)\nclass Success: value: str\n"
        "@dataclass(frozen=True, slots=True)\nclass Failure: reason: str\n"
        f"def load() -> {return_type}:\n"
        "    try:\n        return Success('ok')\n"
        f"    except Exception:\n        return {handler_return}\n"
    )


def test_typed_outcome_accepts_frozen_slotted_union_constructor(tmp_path: Path) -> None:
    result = check(outcome_source("Success | Failure", "Failure('failed')"), [ENTRY], tmp_path)

    assert result.returncode == 0


@pytest.mark.parametrize(
    ("return_type", "handler_return"),
    [
        ("int", "1"),
        ("Success", "result"),
        ("Mutable", "Mutable()"),
        ("dict[str, str]", "{}"),
        ("Success | Failure", "Other()"),
    ],
)
def test_typed_outcome_rejects_non_variant_returns(
    tmp_path: Path, return_type: str, handler_return: str
) -> None:
    result = check(outcome_source(return_type, handler_return), [ENTRY], tmp_path)

    assert result.returncode == 2


@pytest.mark.parametrize("symbol", ("sample.load", "sample.missing"))
def test_typed_outcome_rejects_missing_annotation_or_stale_symbol(
    tmp_path: Path, symbol: str
) -> None:
    source = "def load():\n    try:\n        pass\n    except Exception:\n        return None\n"
    entry = ENTRY | {"symbol": symbol}

    result = check(source, [entry], tmp_path)

    assert result.returncode == 2


@pytest.mark.parametrize(
    "handler_body",
    (
        "def nested() -> Failure:\n            return Failure('nested')",
        "class Nested:\n            def recover(self) -> Failure:\n"
        "                return Failure('nested')",
        "if retry:\n            return Failure('retry')",
    ),
)
def test_typed_outcome_rejects_nested_or_fallthrough_handler_paths(
    tmp_path: Path, handler_body: str
) -> None:
    # Given: a handler with a qualifying nested return or an uncovered normal path.
    source = outcome_handler_source(handler_body)

    # When: the catch boundary claims typed outcomes.
    result = check(source, [ENTRY], tmp_path)

    # Then: neither declaration can suppress its CATCH001 finding.
    assert result.returncode == 2


def test_typed_outcome_rejects_one_bad_branch_and_accepts_exhaustive_branches(
    tmp_path: Path,
) -> None:
    # Given: one handler has an invalid branch while the other returns variants on every path.
    bad = outcome_handler_source("if retry:\n            return Failure('retry')\n        return 1")
    valid = outcome_handler_source(
        "if retry:\n            return Failure('retry')\n        return Success('recovered')"
    )

    # When: both handlers are validated against the typed-outcome obligation.
    bad_result = check(bad, [ENTRY], tmp_path)
    valid_result = check(valid, [ENTRY], tmp_path)

    # Then: every terminal normal path must construct a declared variant.
    assert bad_result.returncode == 2
    assert valid_result.returncode == 0


@pytest.mark.parametrize(
    ("handler_body", "returncode"),
    (
        (
            "try:\n            return Failure('failed')\n        finally:\n            pass",
            0,
        ),
        (
            "try:\n            return Failure('failed')\n        finally:\n            return 1",
            2,
        ),
        (
            "try:\n            return Failure('failed')\n        finally:\n"
            "            raise RuntimeError()",
            2,
        ),
        ("try:\n            pass\n        finally:\n            return Failure('failed')", 0),
        ("raise", 2),
        ("raise RuntimeError()", 2),
    ),
)
def test_typed_outcome_models_finally_overrides_and_rejects_raises(
    tmp_path: Path, handler_body: str, returncode: int
) -> None:
    # Given: a handler whose final body either preserves or replaces its prior exit.
    source = outcome_handler_source(handler_body)

    # When: the checker validates the typed-outcome boundary.
    result = check(source, [ENTRY], tmp_path)

    # Then: only a final normal exit returning a declared outcome is exempted.
    assert result.returncode == returncode


def outcome_handler_source(handler_body: str) -> str:
    return (
        "from dataclasses import dataclass\n"
        "@dataclass(frozen=True, slots=True)\nclass Success: value: str\n"
        "@dataclass(frozen=True, slots=True)\nclass Failure: reason: str\n"
        "def load() -> Success | Failure:\n"
        "    try:\n        return Success('ok')\n"
        "    except Exception:\n"
        f"        {handler_body}\n"
    )
