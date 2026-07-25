from __future__ import annotations

import ast
from dataclasses import dataclass

BUILTINS = frozenset({"Exception", "BaseException", "RuntimeError", "ValueError", "object"})


class Scope:
    __slots__ = ("parent", "kind", "values", "globals", "nonlocals")

    def __init__(self, parent: Scope | None, kind: str) -> None:
        self.parent = parent
        self.kind = kind
        self.values: dict[str, str | None] = {}
        self.globals: set[str] = set()
        self.nonlocals: set[str] = set()

    def resolve(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return self.lookup(node.id)
        if isinstance(node, ast.Attribute):
            parent = self.resolve(node.value)
            return f"{parent}.{node.attr}" if parent else None
        return None

    def lookup(self, name: str) -> str | None:
        if name in self.values:
            return self.values[name]
        parent = self.parent
        if self.kind in {"function", "comprehension"} and parent and parent.kind == "class":
            parent = parent.parent
        if parent:
            return parent.lookup(name)
        return f"builtins.{name}" if name in BUILTINS else None

    def write(self, name: str, value: str | None = None) -> None:
        self.write_scope(name).values[name] = value

    def clear(self, name: str) -> None:
        self.write(name)

    def write_scope(self, name: str) -> Scope:
        if name in self.globals:
            return self.root()
        if name in self.nonlocals:
            return self.enclosing_function()
        return self

    def root(self) -> Scope:
        scope = self
        while scope.parent:
            scope = scope.parent
        return scope

    def enclosing_function(self) -> Scope:
        scope = self.parent
        while scope and scope.kind not in {"function", "module"}:
            scope = scope.parent
        return scope or self.root()


@dataclass(frozen=True, slots=True)
class BindingPlan:
    names: frozenset[str]
    globals: frozenset[str]
    nonlocals: frozenset[str]


class LocalBindings(ast.NodeVisitor):
    def __init__(self) -> None:
        self.names: set[str] = set()
        self.globals: set[str] = set()
        self.nonlocals: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.names.add(node.id)

    def visit_Import(self, node: ast.Import) -> None:
        self.names.update(item.asname or item.name.split(".")[0] for item in node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.names.update(item.asname or item.name for item in node.names if item.name != "*")

    def visit_Global(self, node: ast.Global) -> None:
        self.globals.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self.nonlocals.update(node.names)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.names.add(node.name)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.names.add(node.name)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.names.add(node.name)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return None

    def visit_ListComp(self, node: ast.ListComp) -> None:
        return None

    def visit_SetComp(self, node: ast.SetComp) -> None:
        return None

    def visit_DictComp(self, node: ast.DictComp) -> None:
        return None

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        return None

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        if node.name:
            self.names.add(node.name)
        if node.pattern:
            self.visit(node.pattern)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        if node.name:
            self.names.add(node.name)


def plan_bindings(body: list[ast.stmt], arguments: ast.arguments | None = None) -> BindingPlan:
    visitor = LocalBindings()
    for statement in body:
        visitor.visit(statement)
    if arguments:
        visitor.names.update(argument.arg for argument in all_arguments(arguments))
    return BindingPlan(
        frozenset(visitor.names - visitor.globals - visitor.nonlocals),
        frozenset(visitor.globals),
        frozenset(visitor.nonlocals),
    )


def all_arguments(arguments: ast.arguments) -> tuple[ast.arg, ...]:
    return tuple(
        [
            *arguments.posonlyargs,
            *arguments.args,
            *arguments.kwonlyargs,
            *(item for item in (arguments.vararg, arguments.kwarg) if item),
        ]
    )


def bind_target(scope: Scope, target: ast.AST, value: str | None = None) -> None:
    match target:
        case ast.Name(id=name):
            scope.write(name, value)
        case ast.Starred(value=child):
            bind_target(scope, child, value)
        case ast.Tuple(elts=items) | ast.List(elts=items):
            for item in items:
                bind_target(scope, item, value)
        case ast.MatchAs(name=name) if name:
            scope.write(name, value)
        case ast.MatchStar(name=name) if name:
            scope.write(name, value)
        case ast.MatchSequence(patterns=items) | ast.MatchOr(patterns=items):
            for item in items:
                bind_target(scope, item, value)
        case ast.MatchMapping(rest=name) if name:
            scope.write(name, value)
        case ast.MatchMapping(patterns=items):
            for item in items:
                bind_target(scope, item, value)
        case ast.MatchClass(patterns=items, kwd_patterns=keywords):
            for item in [*items, *keywords]:
                bind_target(scope, item, value)
