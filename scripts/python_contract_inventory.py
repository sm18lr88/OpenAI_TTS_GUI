from __future__ import annotations

import ast
import re
import tokenize
from io import StringIO
from pathlib import Path

from python_contract_boundaries import exemptions, validate
from python_contract_documents import (
    BoundaryDocument,
    BoundaryEntry,
    ContractDocumentError,
    Finding,
)
from python_contract_rules import ContractVisitor, lazy_lines
from python_contract_syntax import module_name, repository_root

IGNORE = re.compile(r"^#\s*type:\s*ignore(?:\[[^\]]+\])?\s*$")


def files(values: list[str]) -> list[Path]:
    found: set[Path] = set()
    for value in values:
        path = Path(value).resolve()
        if not path.exists():
            raise ContractDocumentError
        if path.is_file() and path.suffix == ".py":
            found.add(path)
        elif path.is_dir():
            found.update(item.resolve() for item in path.rglob("*.py"))
        else:
            raise ContractDocumentError
    if not found:
        raise ContractDocumentError
    return sorted(found)


def root(paths: list[Path]) -> Path:
    return repository_root(paths)


def module_inventory(paths: list[Path]) -> frozenset[str]:
    return frozenset(
        name.removesuffix(".__init__") for path in paths if (name := module_name(path))
    )


def boundaries(document: BoundaryDocument, paths: list[Path]) -> tuple[BoundaryEntry, ...]:
    return validate(document, paths)


def scan(
    path: Path,
    root_path: Path,
    declared: tuple[BoundaryEntry, ...],
    modules: frozenset[str],
) -> list[Finding]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    visitor = ContractVisitor(
        path, root_path, lazy_lines(tree), modules, exemptions(declared, path, root_path)
    )
    visitor.visit(tree)
    for token in tokenize.generate_tokens(StringIO(text).readline):
        if token.type == tokenize.COMMENT and IGNORE.fullmatch(token.string):
            visitor.findings.append(
                Finding(
                    "IGNORE001",
                    path.relative_to(root_path).as_posix(),
                    token.start[0],
                    token.string,
                )
            )
    return visitor.findings
