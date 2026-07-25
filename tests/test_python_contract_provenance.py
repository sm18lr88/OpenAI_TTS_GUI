from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.python_contract_provenance_fixtures import (
    REVISION,
    copy_tooling,
    detached_clone,
    initialize_repository,
    run_contract,
    run_size,
)

ROOT = Path(__file__).resolve().parents[1]

CONTRACT_SEMANTIC_MODULES = (
    "check_python_contracts.py",
    *tuple(sorted(path.name for path in (ROOT / "scripts").glob("python_contract_*.py"))),
)


@pytest.mark.parametrize("target", ("rules", "boundaries", *CONTRACT_SEMANTIC_MODULES))
def test_contract_ratchet_rejects_each_authenticated_input_mutation(
    tmp_path: Path, target: str
) -> None:
    # Given: a clean repository and a valid public-CLI baseline.
    root = tmp_path / "repository"
    root.mkdir()
    (root / "source.py").write_text(
        (
            "class State:\n    def __init__(self) -> None:\n        self.value = 1\n"
            "    def advance(self) -> None:\n        self.value += 1\n"
        ),
        encoding="utf-8",
    )
    initialize_repository(root)
    tooling = copy_tooling(tmp_path / "tooling")
    baseline = tmp_path / "baseline.json"
    written = run_contract(tooling, (root,), "--write-baseline", str(baseline))

    # When: one bound rules, boundary, or checker-source input changes.
    match target:
        case "rules":
            rules = json.loads(tooling.rules.read_text(encoding="utf-8"))
            rules["rules"].reverse()
            tooling.rules.write_text(json.dumps(rules), encoding="utf-8")
        case "boundaries":
            tooling.boundaries.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "entries": [
                            {
                                "path": "source.py",
                                "symbol": "source.State",
                                "kind": "mutable_state",
                                "rationale": "fixture state",
                                "obligation": "post_construction_field_mutation",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
        case module:
            source = tooling.contract.parent / module
            source.write_text(
                source.read_text(encoding="utf-8") + "\n# mutation\n", encoding="utf-8"
            )
    result = run_contract(
        tooling, (root,), "--baseline", str(baseline), "--fail-on-new-or-worsened"
    )

    # Then: baseline loading rejects the changed authenticated input.
    assert written.returncode == 0, written.stderr
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"error": "invalid_baseline"}


@pytest.mark.parametrize(
    ("state", "expected_error"),
    [
        ("revision", "invalid_generation"),
        ("dirty", "invalid_generation"),
        ("untracked", "invalid_generation"),
        ("ignored_python", "invalid_generation"),
        ("mixed", "invalid_generation"),
        ("outside", "invalid_generation"),
        ("missing", "invalid_roots"),
        ("empty", "invalid_roots"),
    ],
)
def test_generation_rejects_invalid_git_provenance(
    tmp_path: Path, state: str, expected_error: str
) -> None:
    # Given: a repository root, except for the requested invalid provenance state.
    root = tmp_path / "repository"
    root.mkdir()
    source = root / "source.py"
    source.write_text("value: int = 1\n", encoding="utf-8")
    initialize_repository(root)
    tooling = copy_tooling(tmp_path / "tooling")
    roots = (root,)
    extra: tuple[str, ...] = ()
    match state:
        case "revision":
            extra = ("--source-revision", "0" * 40)
        case "dirty":
            source.write_text("value: int = 2\n", encoding="utf-8")
        case "untracked":
            (root / "new.py").write_text("value: int = 2\n", encoding="utf-8")
        case "ignored_python":
            (root / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
            initialize_repository(root)
            (root / "ignored.py").write_text("value: int = 2\n", encoding="utf-8")
        case "mixed":
            other = tmp_path / "other"
            other.mkdir()
            (other / "other.py").write_text("value: int = 2\n", encoding="utf-8")
            initialize_repository(other)
            roots = (root, other)
        case "outside":
            outside = tmp_path / "outside"
            outside.mkdir()
            (outside / "outside.py").write_text("value: int = 2\n", encoding="utf-8")
            roots = (outside,)
        case "missing":
            roots = (tmp_path / "missing",)
        case "empty":
            empty = tmp_path / "empty"
            empty.mkdir()
            (empty / "README.txt").write_text("fixture\n", encoding="utf-8")
            initialize_repository(empty)
            roots = (empty,)

    # When: generation derives and validates Git provenance through the public CLI.
    result = run_contract(
        tooling, roots, "--write-baseline", str(tmp_path / "baseline.json"), *extra
    )

    # Then: no invalid state can produce a baseline.
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"error": expected_error}


def test_detached_historical_clones_produce_identical_unbaselined_inventory(tmp_path: Path) -> None:
    # Given: two detached local clones at the required historical revision.
    tooling = copy_tooling(tmp_path / "tooling")
    first = detached_clone(tmp_path / "first")
    second = detached_clone(tmp_path / "second")
    first_roots = (first / "src" / "openai_tts_gui", first / "tests", first / "scripts")
    second_roots = (second / "src" / "openai_tts_gui", second / "tests", second / "scripts")

    # When: the current checkers scan both historical clones without a debt baseline.
    contract_results = (
        run_contract(tooling, first_roots),
        run_contract(tooling, second_roots),
    )
    size_results = (
        run_size(tooling, first_roots),
        run_size(tooling, second_roots),
    )

    # Then: authenticated checker semantics produce path-independent inventories.
    assert [result.returncode for result in contract_results] == [1, 1]
    assert [result.returncode for result in size_results] == [1, 1]
    assert json.loads(contract_results[0].stdout) == json.loads(contract_results[1].stdout)
    assert json.loads(size_results[0].stdout) == json.loads(size_results[1].stdout)
    assert REVISION == "55ebba7be4d833893d2872bb72ca3a48ac851977"
