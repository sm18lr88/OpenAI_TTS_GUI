from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.python_contract_provenance_fixtures import (
    copy_tooling,
    initialize_repository,
    run_size,
)

SIZE_SEMANTIC_MODULES = ("check_python_module_size.py", "python_contract_provenance.py")


@pytest.mark.parametrize("module", SIZE_SEMANTIC_MODULES)
def test_size_ratchet_rejects_size_checker_semantics_mutation(tmp_path: Path, module: str) -> None:
    # Given: a clean repository and a public-CLI size baseline.
    root = tmp_path / "repository"
    root.mkdir()
    (root / "source.py").write_text("value: int = 1\n", encoding="utf-8")
    initialize_repository(root)
    tooling = copy_tooling(tmp_path / "tooling")
    baseline = tmp_path / "baseline.json"
    written = run_size(tooling, (root,), "--write-baseline", str(baseline))

    # When: the size checker source changes after baseline creation.
    source = tooling.size.parent / module
    source.write_text(source.read_text(encoding="utf-8") + "\n# mutation\n", encoding="utf-8")
    result = run_size(tooling, (root,), "--baseline", str(baseline), "--fail-on-new-or-worsened")

    # Then: baseline loading rejects the semantic mismatch.
    assert written.returncode == 0, written.stderr
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"error": "invalid_baseline"}
