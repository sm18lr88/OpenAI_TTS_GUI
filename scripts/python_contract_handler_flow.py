from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass

GENERIC_ERRORS = frozenset({"Exception", "BaseException", "RuntimeError", "ValueError"})
SCOPES = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.GeneratorExp)
TERMINALS = (ast.Return, ast.Raise, ast.Break, ast.Continue)


@dataclass(frozen=True, slots=True)
class HandlerExit:
    node: ast.Return | ast.Raise | ast.Break | ast.Continue | None
    logged: bool


def handlers_in(owner: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[ast.ExceptHandler, ...]:
    return tuple(handler for statement in owner.body for handler in nested_handlers(statement))


def nested_handlers(node: ast.AST) -> Iterator[ast.ExceptHandler]:
    if isinstance(node, SCOPES):
        return
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.ExceptHandler):
            yield child
        yield from nested_handlers(child)


def returns_outcome(handler: ast.ExceptHandler, variants: frozenset[str]) -> bool:
    exits = handler_exits(handler)
    return bool(exits) and all(returns_variant(exit_.node, variants) for exit_ in exits)


def logs_and_raises_domain_error(handler: ast.ExceptHandler) -> bool:
    exits = handler_exits(handler)
    return bool(exits) and all(
        exit_.logged and isinstance(exit_.node, ast.Raise) and domain_error(exit_.node)
        for exit_ in exits
    )


def handler_exits(handler: ast.ExceptHandler) -> tuple[HandlerExit, ...]:
    return statement_exits(handler.body, (HandlerExit(node=None, logged=False),))


def statement_exits(
    statements: list[ast.stmt], paths: tuple[HandlerExit, ...]
) -> tuple[HandlerExit, ...]:
    current = paths
    for statement in statements:
        next_paths: list[HandlerExit] = []
        for path in current:
            if path.node is None:
                next_paths.extend(statement_exit_paths(statement, path))
            else:
                next_paths.append(path)
        current = tuple(next_paths)
    return current


def statement_exit_paths(statement: ast.stmt, path: HandlerExit) -> tuple[HandlerExit, ...]:
    if isinstance(statement, TERMINALS):
        return (HandlerExit(node=statement, logged=path.logged),)
    if isinstance(statement, ast.If):
        return statement_exits(statement.body, (path,)) + statement_exits(statement.orelse, (path,))
    if isinstance(statement, ast.Match):
        cases = tuple(
            exit_ for case in statement.cases for exit_ in statement_exits(case.body, (path,))
        )
        return cases if match_is_exhaustive(statement) else cases + (path,)
    if isinstance(statement, (ast.For, ast.AsyncFor, ast.While)):
        loop_paths = (path,) + statement_exits(statement.body, (path,))
        return statement_exits(statement.orelse, loop_paths)
    if isinstance(statement, (ast.With, ast.AsyncWith)):
        return statement_exits(statement.body, (path,))
    if isinstance(statement, (ast.Try, ast.TryStar)):
        body_paths = statement_exits(statement.body, (path,))
        normal_paths = statement_exits(statement.orelse, body_paths)
        caught_paths = tuple(
            exit_
            for handler in statement.handlers
            for exit_ in statement_exits(handler.body, (path,))
        )
        return finalbody_exits(statement.finalbody, normal_paths + caught_paths)
    if isinstance(statement, SCOPES):
        return (path,)
    return (HandlerExit(node=None, logged=path.logged or has_logger_call(statement)),)


def match_is_exhaustive(statement: ast.Match) -> bool:
    return any(
        isinstance(case.pattern, ast.MatchAs)
        and case.pattern.pattern is None
        and case.guard is None
        for case in statement.cases
    )


def finalbody_exits(
    statements: list[ast.stmt], paths: tuple[HandlerExit, ...]
) -> tuple[HandlerExit, ...]:
    return tuple(
        HandlerExit(
            node=final.node if final.node is not None else path.node,
            logged=final.logged,
        )
        for path in paths
        for final in statement_exits(statements, (HandlerExit(node=None, logged=path.logged),))
    )


def returns_variant(
    node: ast.Return | ast.Raise | ast.Break | ast.Continue | None, variants: frozenset[str]
) -> bool:
    return (
        isinstance(node, ast.Return)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id in variants
    )


def has_logger_call(node: ast.AST) -> bool:
    if isinstance(node, SCOPES):
        return False
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and logger_name(node.func.value)
    ):
        return True
    return any(has_logger_call(child) for child in ast.iter_child_nodes(node))


def logger_name(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return node.id.endswith("logger")
    return isinstance(node, ast.Attribute) and node.attr.endswith("logger")


def domain_error(node: ast.Raise) -> bool:
    if node.exc is None:
        return False
    target = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
    if isinstance(target, ast.Name):
        name = target.id
    elif isinstance(target, ast.Attribute):
        name = target.attr
    else:
        return False
    return name not in GENERIC_ERRORS and name.endswith("Error")
