from __future__ import annotations

import ast

from python_contract_scope import Scope, all_arguments, bind_target, plan_bindings
from python_contract_syntax import import_target


class Resolver(ast.NodeVisitor):
    def __init__(self, module_inventory: frozenset[str], module: str = "") -> None:
        self.scope = Scope(None, "module")
        self.module_inventory = module_inventory
        self.module = module

    def push(self, kind: str, plan: tuple[list[ast.stmt], ast.arguments | None]) -> Scope:
        previous = self.scope
        bindings = plan_bindings(*plan)
        self.scope = Scope(previous, kind)
        self.scope.globals.update(bindings.globals)
        self.scope.nonlocals.update(bindings.nonlocals)
        self.scope.values.update(dict.fromkeys(bindings.names))
        return previous

    def pop(self, previous: Scope) -> None:
        self.scope = previous

    def push_type_parameters(self, parameters: list[ast.type_param]) -> Scope:
        previous = self.scope
        self.scope = Scope(previous, "type")
        for parameter in parameters:
            self.scope.write(type_parameter_name(parameter))
        return previous

    def bind(self, target: ast.AST, value: str | None = None) -> None:
        bind_target(self.scope, target, value)

    def visit_Import(self, node: ast.Import) -> None:
        for item in node.names:
            self.scope.write(item.asname or item.name.split(".")[0], item.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        base = import_target(node, self.module)
        for item in node.names:
            if item.name != "*":
                target = f"{base}.{item.name}" if base else item.name
                self.scope.write(item.asname or item.name, target)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        for target in node.targets:
            self.bind(target)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.visit(node.annotation)
        if node.value:
            self.visit(node.value)
        self.bind(node.target)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.visit(node.target)
        self.visit(node.value)
        self.bind(node.target)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.visit(node.value)
        self.bind(node.target)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            self.bind(target)

    def visit_For(self, node: ast.For) -> None:
        self.visit(node.iter)
        self.bind(node.target)
        for statement in [*node.body, *node.orelse]:
            self.visit(statement)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.visit(node.iter)
        self.bind(node.target)
        for statement in [*node.body, *node.orelse]:
            self.visit(statement)

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars:
                self.bind(item.optional_vars)
        for statement in node.body:
            self.visit(statement)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars:
                self.bind(item.optional_vars)
        for statement in node.body:
            self.visit(statement)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type:
            self.visit(node.type)
        if node.name:
            self.scope.write(node.name)
        for statement in node.body:
            self.visit(statement)
        if node.name:
            self.scope.clear(node.name)

    def visit_Match(self, node: ast.Match) -> None:
        self.visit(node.subject)
        for case in node.cases:
            bind_target(self.scope, case.pattern)
            if case.guard:
                self.visit(case.guard)
            for statement in case.body:
                self.visit(statement)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._function(node)

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        self.visit_defaults(node.args)
        type_parameters = self.push_type_parameters(node.type_params)
        self.visit_type_parameters(node.type_params)
        self.visit_annotations(node.args, node.returns)
        self.pop(type_parameters)
        self.scope.write(node.name)
        previous = self.push("function", (node.body, node.args))
        for parameter in node.type_params:
            self.scope.write(type_parameter_name(parameter))
        for argument in all_arguments(node.args):
            self.scope.write(argument.arg)
        for statement in node.body:
            self.visit(statement)
        self.pop(previous)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self.visit_defaults(node.args)
        previous = self.push("function", ([], node.args))
        for argument in all_arguments(node.args):
            self.scope.write(argument.arg)
        self.visit(node.body)
        self.pop(previous)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        self.scope.write(node.name)
        type_parameters = self.push_type_parameters(node.type_params)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword.value)
        self.visit_type_parameters(node.type_params)
        previous = self.push("class", (node.body, None))
        for statement in node.body:
            self.visit(statement)
        self.pop(previous)
        self.pop(type_parameters)

    def visit_TypeAlias(self, node: ast.TypeAlias) -> None:
        self.bind(node.name)
        previous = self.push_type_parameters(node.type_params)
        self.visit_type_parameters(node.type_params)
        self.visit_type_alias_value(node)
        self.pop(previous)

    def visit_type_alias_value(self, node: ast.TypeAlias) -> None:
        self.visit_annotation(node.value)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self.comprehension(node.generators, (node.elt,))

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self.comprehension(node.generators, (node.elt,))

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self.comprehension(node.generators, (node.elt,))

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self.comprehension(node.generators, (node.key, node.value))

    def comprehension(
        self, generators: list[ast.comprehension], values: tuple[ast.AST, ...]
    ) -> None:
        previous = self.push("comprehension", ([], None))
        for generator in generators:
            self.visit(generator.iter)
            self.bind(generator.target)
            for condition in generator.ifs:
                self.visit(condition)
        for value in values:
            self.visit(value)
        self.pop(previous)

    def visit_defaults(self, arguments: ast.arguments) -> None:
        for value in [*arguments.defaults, *arguments.kw_defaults]:
            if value:
                self.visit(value)

    def visit_annotations(self, arguments: ast.arguments, returns: ast.expr | None) -> None:
        for argument in all_arguments(arguments):
            if argument.annotation:
                self.visit_annotation(argument.annotation)
        if returns:
            self.visit_annotation(returns)

    def visit_type_parameters(self, parameters: list[ast.type_param]) -> None:
        for parameter in parameters:
            for expression in type_parameter_expressions(parameter):
                self.visit_annotation(expression)

    def visit_annotation(self, node: ast.expr) -> None:
        self.visit(node)


def type_parameter_name(parameter: ast.type_param) -> str:
    match parameter:
        case ast.TypeVar() | ast.ParamSpec() | ast.TypeVarTuple():
            return parameter.name
        case _:
            raise AssertionError


def type_parameter_expressions(parameter: ast.type_param) -> tuple[ast.expr, ...]:
    match parameter:
        case ast.TypeVar(bound=bound, default_value=default):
            return tuple(item for item in (bound, default) if item)
        case ast.ParamSpec(default_value=default):
            return (default,) if default else ()
        case ast.TypeVarTuple(default_value=default):
            return (default,) if default else ()
        case _:
            raise AssertionError
