from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVISION = "55ebba7be4d833893d2872bb72ca3a48ac851977"


@dataclass(frozen=True, slots=True)
class Tooling:
    contract: Path
    size: Path
    rules: Path
    boundaries: Path


def copy_tooling(destination: Path) -> Tooling:
    scripts = destination / "scripts"
    scripts.mkdir(parents=True)
    for source in (ROOT / "scripts").glob("python_contract_*.py"):
        shutil.copyfile(source, scripts / source.name)
    for name in ("check_python_contracts.py", "check_python_module_size.py"):
        shutil.copyfile(ROOT / "scripts" / name, scripts / name)
    rules = scripts / "python_contract_rules.json"
    boundaries = destination / "boundaries.json"
    shutil.copyfile(ROOT / "quality" / "python" / "rules.json", rules)
    boundaries.write_text('{"version": 1, "entries": []}\n', encoding="utf-8")
    return Tooling(
        scripts / "check_python_contracts.py",
        scripts / "check_python_module_size.py",
        rules,
        boundaries,
    )


def run_contract(
    tooling: Tooling, roots: tuple[Path, ...], *extra: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(tooling.contract),
            *(str(root) for root in roots),
            "--rules",
            str(tooling.rules),
            "--boundaries",
            str(tooling.boundaries),
            *extra,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def run_size(
    tooling: Tooling, roots: tuple[Path, ...], *extra: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(tooling.size), *(str(root) for root in roots), *extra],
        check=False,
        capture_output=True,
        text=True,
    )


def initialize_repository(root: Path) -> None:
    for command in (
        ("init",),
        ("add", "."),
        (
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "fixture",
        ),
    ):
        git(root, *command)


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    )


def detached_clone(destination: Path) -> Path:
    subprocess.run(
        ["git", "clone", "--no-local", "--no-checkout", str(ROOT), str(destination)],
        check=True,
        capture_output=True,
        text=True,
    )
    git(destination, "checkout", "--detach", REVISION)
    return destination
