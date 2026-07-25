from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_python_contracts.py"
RULES = ROOT / "quality" / "python" / "rules.json"


def check(root: Path) -> set[str]:
    boundaries = root / "boundaries.json"
    boundaries.write_text('{"version": 1, "entries": []}', encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(root),
            "--rules",
            str(RULES),
            "--boundaries",
            str(boundaries),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    return {item["rule_id"] for item in json.loads(result.stdout)["findings"]}


@pytest.mark.parametrize(
    "source",
    [
        "from ._compat import TTSProcessor\n",
        "def other(name):\n    if name == 'TTSProcessor':\n"
        "        from ._compat import TTSProcessor\n",
        "def __getattr__(name):\n    if name == 'Other':\n"
        "        from ._compat import TTSProcessor\n",
        "def __getattr__(name):\n    if name == 'TTSProcessor':\n"
        "        from ._compat import TTSProcessor, Other\n",
        "def __getattr__(name):\n    if name == 'TTSProcessor':\n"
        "        from ._compat import TTSProcessor\n        return Other\n",
    ],
)
def test_bridge_rejects_noncanonical_compat_projection(tmp_path: Path, source: str) -> None:
    # Given: a TTS package compatibility import outside the exact lazy projection.
    package = tmp_path / "src" / "openai_tts_gui" / "tts"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(source, encoding="utf-8")

    # When: the contract checker scans it.
    # Then: the alternate bridge is reported.
    assert "QTBRIDGE001" in check(tmp_path)


def test_var_chain_emits_one_outer_canonical_finding(tmp_path: Path) -> None:
    # Given: a four-way equality chain on one scrutinee.
    source = tmp_path / "chain.py"
    source.write_text(
        "if value == 1:\n    pass\nelif value == 2:\n    pass\n"
        "elif value == 3:\n    pass\nelif value == 4:\n    pass\n",
        encoding="utf-8",
    )

    # When: the checker scans nested elif AST nodes.
    # Then: exactly one VAR001 finding fingerprints the whole outer chain.
    boundaries = tmp_path / "boundaries.json"
    boundaries.write_text('{"version": 1, "entries": []}', encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(source),
            "--rules",
            str(RULES),
            "--boundaries",
            str(boundaries),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    findings = [
        item for item in json.loads(result.stdout)["findings"] if item["rule_id"] == "VAR001"
    ]
    assert len(findings) == 1
    assert findings[0]["fingerprint"].startswith("If(")
