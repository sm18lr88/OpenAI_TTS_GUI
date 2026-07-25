from __future__ import annotations

import ast

from python_contract_handler_flow import handlers_in, returns_outcome


def typed_outcome(tree: ast.Module, owner: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    variants = outcome_variants(owner.returns)
    if len(variants) < 2:
        return False
    classes = {item.name: item for item in tree.body if isinstance(item, ast.ClassDef)}
    if any(name not in classes or not frozen_slots(classes[name]) for name in variants):
        return False
    handlers = handlers_in(owner)
    return bool(handlers) and all(returns_outcome(handler, variants) for handler in handlers)


def outcome_variants(node: ast.expr | None) -> frozenset[str]:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return outcome_variants(node.left) | outcome_variants(node.right)
    return frozenset({node.id}) if isinstance(node, ast.Name) else frozenset()


def frozen_slots(node: ast.ClassDef) -> bool:
    return any(
        isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Name)
        and decorator.func.id == "dataclass"
        and enabled_dataclass_fields(decorator) >= {"frozen", "slots"}
        for decorator in node.decorator_list
    )


def enabled_dataclass_fields(decorator: ast.Call) -> set[str | None]:
    return {
        keyword.arg
        for keyword in decorator.keywords
        if isinstance(keyword.value, ast.Constant) and keyword.value.value is True
    }
