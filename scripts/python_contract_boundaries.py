from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

from python_contract_documents import BoundaryDocument, BoundaryEntry, ContractDocumentError
from python_contract_handler_flow import handlers_in, logs_and_raises_domain_error
from python_contract_outcomes import typed_outcome
from python_contract_syntax import module_name, relative_path, repository_root

MUTABLE_OBLIGATION = "post_construction_field_mutation"
CATCH_OBLIGATIONS = frozenset({"typed_outcome", "log_and_domain_error"})


def validate(document: BoundaryDocument, paths: list[Path]) -> tuple[BoundaryEntry, ...]:
    root = repository_root(paths)
    normalized = [relative_path(path, root) for path in paths]
    if len(set(normalized)) != len(paths):
        raise ContractDocumentError
    available = dict(zip(normalized, paths, strict=True))
    seen: set[tuple[str, str]] = set()
    for entry in document.entries:
        if (entry.path, entry.symbol) in seen or entry.path not in available:
            raise ContractDocumentError
        seen.add((entry.path, entry.symbol))
        source = available[entry.path]
        tree = ast.parse(source.read_text(encoding="utf-8"))
        owner = owner_for(source, entry.symbol)
        if entry.kind == "mutable_state":
            valid = isinstance(owner, ast.ClassDef) and mutates(owner)
        elif entry.kind == "catch_boundary":
            valid = isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef)) and catches(
                owner, entry.obligation, tree
            )
        else:
            valid = False
        if not valid:
            raise ContractDocumentError
    return document.entries


def exemptions(
    entries: tuple[BoundaryEntry, ...], path: Path, root: Path
) -> frozenset[tuple[str, str]]:
    return frozenset(
        ("DATA001" if entry.kind == "mutable_state" else "CATCH001", entry.symbol)
        for entry in entries
        if entry.path == relative_path(path, root)
    )


def owner_for(path: Path, symbol: str) -> ast.AST:
    module = module_name(path)
    if not symbol.startswith(f"{module}."):
        raise ContractDocumentError
    tree = ast.parse(path.read_text(encoding="utf-8"))
    owners = dict(named_owners(tree.body, module))
    try:
        return owners[symbol]
    except KeyError as error:
        raise ContractDocumentError from error


def named_owners(statements: list[ast.stmt], prefix: str) -> Iterator[tuple[str, ast.AST]]:
    for statement in statements:
        if isinstance(statement, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            symbol = f"{prefix}.{statement.name}"
            yield symbol, statement
            yield from named_owners(statement.body, symbol)


def mutates(owner: ast.ClassDef) -> bool:
    return any(
        field_mutation(statement)
        for method in owner.body
        if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
        and method.name not in {"__init__", "__post_init__"}
        for statement in executable(method.body)
    )


def field_mutation(statement: ast.AST) -> bool:
    match statement:
        case ast.Assign() | ast.Delete():
            return any(mutated_self_target(target) for target in statement.targets)
        case ast.AnnAssign() | ast.AugAssign():
            return mutated_self_target(statement.target)
        case _:
            return False


def mutated_self_target(target: ast.AST) -> bool:
    current = target
    while isinstance(current, (ast.Attribute, ast.Subscript)):
        current = current.value
    if isinstance(current, ast.Name):
        return current.id == "self"
    return (
        isinstance(current, ast.Call)
        and isinstance(current.func, ast.Attribute)
        and isinstance(current.func.value, ast.Name)
        and current.func.value.id == "self"
    )


def catches(
    owner: ast.FunctionDef | ast.AsyncFunctionDef, obligation: str | None, tree: ast.Module
) -> bool:
    handlers = handlers_in(owner)
    if not handlers:
        return False
    if obligation == "typed_outcome":
        return typed_outcome(tree, owner)
    if obligation == "log_and_domain_error":
        return all(logs_and_raises_domain_error(handler) for handler in handlers)
    return False


def executable(statements: list[ast.stmt]) -> Iterator[ast.AST]:
    for statement in statements:
        yield statement
        if not isinstance(
            statement, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
        ):
            yield from executable_children(statement)


def executable_children(node: ast.AST) -> Iterator[ast.AST]:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        yield child
        yield from executable_children(child)
