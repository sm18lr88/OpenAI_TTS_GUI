"""Keep test temporary files inside the repository workspace.

Some environments block writes to the OS temporary directory, for example locked-down Windows
profiles. This configuration directs pytest and tempfile to a local folder.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


def _ensure_repo_temp(rootpath: Path) -> Path:
    base = rootpath / ".pytest_tmp"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _default_basetemp(rootpath: Path) -> Path:
    return _ensure_repo_temp(rootpath) / f"pytest-{os.getpid()}"


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    configured_basetemp = config.option.basetemp
    base = (
        Path(str(configured_basetemp))
        if configured_basetemp is not None
        else _default_basetemp(Path(str(config.rootpath)))
    )
    base.mkdir(parents=True, exist_ok=True)
    # Given: pytest must use the local temporary folder before it creates a fixture.
    config.option.basetemp = str(base)
    # Then: tempfile uses the same local temporary folder.
    tempfile.tempdir = str(base)
    os.environ.setdefault("TMPDIR", str(base))
    os.environ.setdefault("TMP", str(base))
    os.environ.setdefault("TEMP", str(base))
