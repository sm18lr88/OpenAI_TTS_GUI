from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Final

from python_contract_documents import ContractDocumentError

CONTRACT_ENTRYPOINT: Final[str] = "check_python_contracts.py"


def contract_modules(directory: Path) -> tuple[str, ...]:
    modules = tuple(sorted(path.name for path in directory.glob("python_contract_*.py")))
    if not modules or CONTRACT_ENTRYPOINT in modules:
        raise ContractDocumentError
    return (CONTRACT_ENTRYPOINT, *modules)


def canonical_hash(path: Path) -> str:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractDocumentError from error
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def source_hash(names: tuple[str, ...], directory: Path) -> str:
    digest = hashlib.sha256()
    ordered = tuple(sorted(names))
    if len(ordered) != len(set(ordered)):
        raise ContractDocumentError
    for name in ordered:
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ContractDocumentError
        path = directory / relative
        try:
            contents = path.read_bytes()
        except OSError as error:
            raise ContractDocumentError from error
        digest.update(relative.as_posix().encode())
        digest.update(b"\0")
        digest.update(contents)
        digest.update(b"\0")
    return digest.hexdigest()


def git_revision(roots: list[str]) -> str:
    paths = [Path(root).resolve() for root in roots]
    if not paths or any(not path.exists() for path in paths):
        raise ContractDocumentError
    worktrees = tuple(_worktree(path) for path in paths)
    root = worktrees[0]
    if any(worktree != root for worktree in worktrees):
        raise ContractDocumentError
    inventory = _python_inventory(paths)
    if not inventory:
        raise ContractDocumentError
    for path in paths:
        relative = path.relative_to(root).as_posix()
        _git(root, "ls-files", "--error-unmatch", "--", relative)
        if _git(root, "status", "--porcelain", "--untracked-files=no", "--", relative):
            raise ContractDocumentError
    for path in inventory:
        relative = path.relative_to(root).as_posix()
        _git(root, "ls-files", "--error-unmatch", "--", relative)
    return _git(root, "rev-parse", "--verify", "HEAD")


def write_document(path: Path, contents: str) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as output:
            temporary = Path(output.name)
            output.write(contents)
        temporary.replace(path)
    except OSError as error:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise ContractDocumentError from error


def _worktree(path: Path) -> Path:
    start = path if path.is_dir() else path.parent
    return Path(_git(start, "rev-parse", "--show-toplevel")).resolve()


def _python_inventory(roots: list[Path]) -> list[Path]:
    files = {
        candidate.resolve()
        for root in roots
        for candidate in ([root] if root.is_file() else root.rglob("*.py"))
        if candidate.suffix == ".py"
    }
    return sorted(files)


def _git(directory: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(directory), *args], check=False, capture_output=True, text=True
    )
    if result.returncode:
        raise ContractDocumentError
    return result.stdout.strip()
