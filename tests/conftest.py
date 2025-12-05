"""Global test configuration to keep temp files inside the repo workspace.

Some environments block writes to the OS temp directory (e.g., locked-down Windows profiles).
We redirect pytest's base temp dir plus stdlib/tempfile to a local folder.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import pytest


def _ensure_repo_temp(rootpath: Path) -> Path:
    base = rootpath / ".pytest_tmp"
    base.mkdir(parents=True, exist_ok=True)
    return base


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: Any) -> None:
    base = _ensure_repo_temp(Path(str(config.rootpath)))
    # Point pytest's tmp_path/tmpdir fixtures to the repo-local temp folder.
    # This is honored when set before the first fixture request.
    config.option.basetemp = str(base)
    # Keep stdlib tempfile aligned as well.
    tempfile.tempdir = str(base)
    os.environ.setdefault("TMPDIR", str(base))
    os.environ.setdefault("TMP", str(base))
    os.environ.setdefault("TEMP", str(base))
