from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_python_contracts.py"
RULES = ROOT / "quality" / "python" / "rules.json"
DOMAIN_ERROR_ENTRY = {
    "path": "sample.py",
    "symbol": "sample.load",
    "kind": "catch_boundary",
    "rationale": "translate external failures",
    "obligation": "log_and_domain_error",
}


def check(
    source: str, entries: list[dict[str, str]], tmp_path: Path
) -> subprocess.CompletedProcess[str]:
    module = tmp_path / "sample.py"
    boundaries = tmp_path / "boundaries.json"
    module.write_text(source, encoding="utf-8")
    boundaries.write_text(json.dumps({"version": 1, "entries": entries}), encoding="utf-8")
    return subprocess.run(
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


def test_exact_mutable_boundary_suppresses_only_its_owned_data_finding(tmp_path: Path) -> None:
    # Given: two mutable dataclasses where only one has a post-construction mutation boundary.
    source = (
        "from dataclasses import dataclass\n"
        "@dataclass\nclass State:\n    def advance(self):\n        self.value = 1\n"
        "@dataclass\nclass Other:\n    def advance(self):\n        self.value = 1\n"
    )
    entry = {
        "path": "sample.py",
        "symbol": "sample.State",
        "kind": "mutable_state",
        "rationale": "state advances after construction",
        "obligation": "post_construction_field_mutation",
    }

    # When: the exact State owner is declared.
    result = check(source, [entry], tmp_path)
    findings = json.loads(result.stdout)["findings"]

    # Then: State is exempt but Other remains a DATA001 violation.
    assert result.returncode == 1
    assert [item["rule_id"] for item in findings] == ["DATA001"]


def test_exact_catch_boundary_requires_and_exempts_domain_conversion(tmp_path: Path) -> None:
    # Given: a logged broad handler that converts to a domain error.
    source = (
        "class DomainError(Exception): pass\n"
        "def load() -> int:\n"
        "    try:\n        return 1\n"
        "    except Exception as error:\n"
        "        logger.warning('load failed: %s', error)\n"
        "        raise DomainError() from error\n"
    )
    entry = {
        "path": "sample.py",
        "symbol": "sample.load",
        "kind": "catch_boundary",
        "rationale": "translate external failures",
        "obligation": "log_and_domain_error",
    }

    # When: the exact handler owner is declared.
    result = check(source, [entry], tmp_path)

    # Then: the validated declaration suppresses its owned CATCH001 only.
    assert result.returncode == 0
    assert json.loads(result.stdout)["findings"] == []


@pytest.mark.parametrize(
    "handler_body",
    (
        "if retry:\n            return\n        logger.warning('load failed')\n"
        "        raise DomainError()",
        "if retry:\n            logger.warning('load failed')\n"
        "            raise DomainError()\n        raise DomainError()",
        "logger.warning('load failed')\n        return",
        "raise DomainError()",
        "def nested() -> None:\n            logger.warning('load failed')\n"
        "            raise DomainError()",
        "nested = lambda: logger.warning('load failed')\n        raise DomainError()",
        "try:\n            logger.warning('load failed')\n            raise DomainError()\n"
        "        finally:\n            return",
    ),
)
def test_domain_error_boundary_rejects_unlogged_or_nonconverting_handler_paths(
    tmp_path: Path, handler_body: str
) -> None:
    # Given: a handler with an early exit, incomplete branch, missing obligation, or nested decoy.
    source = (
        "class DomainError(Exception): pass\n"
        "def load() -> int:\n"
        "    try:\n        return 1\n"
        "    except Exception as error:\n"
        f"        {handler_body}\n"
    )
    # When: the declaration asks to exempt the handler.
    result = check(source, [DOMAIN_ERROR_ENTRY], tmp_path)

    # Then: every terminal path must log before raising a domain error.
    assert result.returncode == 2


def test_domain_error_boundary_accepts_logged_domain_error_on_all_branches(tmp_path: Path) -> None:
    # Given: each branch logs before converting the caught error.
    source = (
        "class DomainError(Exception): pass\n"
        "def load() -> int:\n"
        "    try:\n        return 1\n"
        "    except Exception as error:\n"
        "        if retry:\n"
        "            logger.warning('retry failed')\n"
        "            raise DomainError() from error\n"
        "        logger.warning('load failed')\n"
        "        raise DomainError() from error\n"
    )
    # When: the declaration validates the exhaustive handler.
    result = check(source, [DOMAIN_ERROR_ENTRY], tmp_path)

    # Then: its owned CATCH001 finding is safely exempted.
    assert result.returncode == 0


@pytest.mark.parametrize(
    "entry",
    [
        {
            "path": "sample.py",
            "symbol": "sample.State",
            "kind": "mutable_state",
            "rationale": "missing obligation",
        },
        {
            "path": "sample.py",
            "symbol": "sample.State",
            "kind": "catch_boundary",
            "rationale": "wrong owner kind",
            "obligation": "typed_outcome",
        },
        {
            "path": "sample.py",
            "symbol": "sample.State.advance",
            "kind": "mutable_state",
            "rationale": "wrong owner prefix",
            "obligation": "post_construction_field_mutation",
        },
    ],
)
def test_boundary_schema_rejects_missing_or_wrong_kind_owner(
    tmp_path: Path, entry: dict[str, str]
) -> None:
    # Given: a declaration lacking its kind obligation or naming the wrong qualified owner.
    source = "class State:\n    def advance(self):\n        self.value = 1\n"

    # When: the checker validates the boundary document.
    result = check(source, [entry], tmp_path)

    # Then: malformed exemptions fail closed.
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"error": "invalid_boundaries"}


@pytest.mark.parametrize(
    ("source", "entry"),
    [
        (
            "class State:\n    def advance(self):\n        self.value = 1\n",
            {
                "path": "other.py",
                "symbol": "sample.State",
                "kind": "mutable_state",
                "rationale": "wrong normalized path",
                "obligation": "post_construction_field_mutation",
            },
        ),
        (
            "class State:\n    pass\n",
            {
                "path": "sample.py",
                "symbol": "sample.State",
                "kind": "mutable_state",
                "rationale": "immutable owner",
                "obligation": "post_construction_field_mutation",
            },
        ),
    ],
)
def test_mutable_boundary_rejects_wrong_path_or_immutable_owner(
    tmp_path: Path, source: str, entry: dict[str, str]
) -> None:
    # Given: a declaration that does not name a mutable class in the scanned file.

    # When: the checker validates its boundary declaration.
    result = check(source, [entry], tmp_path)

    # Then: both declarations fail closed rather than widening DATA001 exemptions.
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"error": "invalid_boundaries"}


@pytest.mark.parametrize(
    "statement",
    (
        "self.scope().values['name'] = 1",
        "self.scope().values['name'] += 1",
        "del self.scope().values['name']",
    ),
)
def test_mutable_boundary_accepts_assigned_self_call_result(tmp_path: Path, statement: str) -> None:
    # Given: a mutable class whose post-construction target descends from a self call.
    source = (
        "from dataclasses import dataclass\n"
        "@dataclass\nclass State:\n"
        "    def scope(self):\n        return self\n"
        f"    def advance(self):\n        {statement}\n"
    )
    entry = {
        "path": "sample.py",
        "symbol": "sample.State",
        "kind": "mutable_state",
        "rationale": "state mutates through its own scope result",
        "obligation": "post_construction_field_mutation",
    }

    # When: the exact mutable boundary is validated.
    result = check(source, [entry], tmp_path)

    # Then: assignment, augmentation, and deletion through the self call are accepted.
    assert result.returncode == 0
    assert json.loads(result.stdout)["findings"] == []


@pytest.mark.parametrize(
    "statement",
    (
        "other.scope().values['name'] = 1",
        "self.scope().values['name']",
        "self.scope()",
        "scope = self.scope()\n        scope.values['name'] = 1",
        "factory().values['name'] = 1",
    ),
)
def test_mutable_boundary_rejects_unproven_call_result(tmp_path: Path, statement: str) -> None:
    # Given: a mutable class without a directly assigned result from a self method call.
    source = (
        "from dataclasses import dataclass\n"
        "@dataclass\nclass State:\n"
        "    def scope(self):\n        return self\n"
        f"    def advance(self):\n        {statement}\n"
    )
    entry = {
        "path": "sample.py",
        "symbol": "sample.State",
        "kind": "mutable_state",
        "rationale": "unproven state mutation",
        "obligation": "post_construction_field_mutation",
    }

    # When: the declaration attempts to exempt the class.
    result = check(source, [entry], tmp_path)

    # Then: foreign calls, reads, bare calls, aliases, and arbitrary calls fail closed.
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"error": "invalid_boundaries"}


def test_scope_requires_no_mutable_state_boundary() -> None:
    # Given: the committed Scope source and an empty boundary manifest.
    scope = ROOT / "scripts" / "python_contract_scope.py"
    boundaries = ROOT / "quality" / "python" / "boundaries.json"

    # When: the checker scans only that owner.
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(scope),
            "--rules",
            str(RULES),
            "--boundaries",
            str(boundaries),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    # Then: explicit slots state is not a mutable dataclass violation.
    assert result.returncode == 0
    assert json.loads(result.stdout)["findings"] == []
