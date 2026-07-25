from __future__ import annotations

import ast
import os
from pathlib import Path

from python_contract_documents import Finding


def relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def repository_root(paths: list[Path]) -> Path:
    for path in paths:
        parts = path.parts
        for index in range(len(parts) - 1):
            if parts[index : index + 2] == ("src", "openai_tts_gui"):
                return Path(*parts[:index])
    return Path(os.path.commonpath([str(path.parent) for path in paths]))


def module_name(path: Path) -> str:
    parts = path.with_suffix("").as_posix().split("/")
    if "openai_tts_gui" in parts:
        return ".".join(parts[parts.index("openai_tts_gui") :])
    return path.stem


def record(rule: str, path: Path, root: Path, node: ast.AST, detail: str = "") -> Finding:
    return Finding(
        rule,
        path.relative_to(root).as_posix(),
        getattr(node, "lineno", 1),
        detail or ast.dump(node, include_attributes=False),
    )


def aliases(tree: ast.Module) -> tuple[set[str], set[str], set[str], set[str]]:
    any_names, cast_names, typing_names, data_names = {"Any"}, {"cast"}, {"typing"}, {"dataclass"}
    for node in tree.body:
        if isinstance(node, ast.Import):
            typing_names.update(
                alias.asname or alias.name for alias in node.names if alias.name == "typing"
            )
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            any_names.update(
                alias.asname or alias.name for alias in node.names if alias.name == "Any"
            )
            cast_names.update(
                alias.asname or alias.name for alias in node.names if alias.name == "cast"
            )
        if isinstance(node, ast.ImportFrom) and node.module == "dataclasses":
            data_names.update(
                alias.asname or alias.name for alias in node.names if alias.name == "dataclass"
            )
    return any_names, cast_names, typing_names, data_names


def annotations(tree: ast.Module) -> list[ast.AST]:
    found: list[ast.AST] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.extend(
                arg.annotation
                for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
                if arg.annotation
            )
            if node.args.vararg and node.args.vararg.annotation:
                found.append(node.args.vararg.annotation)
            if node.args.kwarg and node.args.kwarg.annotation:
                found.append(node.args.kwarg.annotation)
            if node.returns:
                found.append(node.returns)
        if isinstance(node, ast.AnnAssign):
            found.append(node.annotation)
        if isinstance(node, ast.TypeAlias):
            found.append(node.value)
    return found


def import_target(node: ast.ImportFrom, module: str) -> str:
    if not node.level:
        return node.module or ""
    package = module.split(".")[:-1]
    return ".".join(package[: len(package) - node.level + 1] + (node.module or "").split("."))


def import_targets(node: ast.Import | ast.ImportFrom, module: str) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    base = import_target(node, module)
    return [f"{base}.{alias.name}" if base else alias.name for alias in node.names]


def frozen_dataclass(node: ast.ClassDef, names: set[str]) -> bool:
    for decorator in node.decorator_list:
        call = decorator if isinstance(decorator, ast.Call) else None
        name = (
            call.func.id
            if call and isinstance(call.func, ast.Name)
            else decorator.id
            if isinstance(decorator, ast.Name)
            else ""
        )
        if name in names:
            return bool(
                call
                and any(
                    keyword.arg == "frozen"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True
                    for keyword in call.keywords
                )
            )
    return True


def equality_chain(node: ast.If) -> str:
    lefts: list[str] = []
    current = node
    while (
        isinstance(current.test, ast.Compare)
        and len(current.test.ops) == 1
        and isinstance(current.test.ops[0], ast.Eq)
    ):
        lefts.append(ast.dump(current.test.left, include_attributes=False))
        if len(current.orelse) != 1 or not isinstance(current.orelse[0], ast.If):
            break
        current = current.orelse[0]
    return (
        ast.dump(node, include_attributes=False) if len(lefts) >= 3 and len(set(lefts)) == 1 else ""
    )
