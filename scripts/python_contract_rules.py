from __future__ import annotations

import ast
from pathlib import Path

from python_contract_documents import Finding
from python_contract_resolution import Resolver
from python_contract_syntax import (
    equality_chain,
    import_target,
    import_targets,
    module_name,
    record,
    relative_path,
)

GENERIC = frozenset({"builtins.Exception", "builtins.RuntimeError", "builtins.ValueError"})
BROAD = frozenset({"builtins.Exception", "builtins.BaseException"})


class ContractVisitor(Resolver):
    def __init__(
        self,
        path: Path,
        root_path: Path,
        lazy_imports: set[int],
        modules: frozenset[str],
        exemptions: frozenset[tuple[str, str]],
    ) -> None:
        module = module_name(path)
        super().__init__(modules, module)
        self.path = path
        self.root_path = root_path
        self.findings: list[Finding] = []
        self.relative = relative_path(path, root_path)
        self.lazy_imports = lazy_imports
        self.exemptions = exemptions
        self.owners: list[str] = []
        self.var_children: set[int] = set()

    def finding(self, rule: str, node: ast.AST, detail: str = "") -> None:
        owner = ".".join([self.module, *self.owners]).strip(".")
        if (rule, owner) not in self.exemptions:
            self.findings.append(record(rule, self.path, self.root_path, node, detail))

    def annotation(self, node: ast.AST) -> None:
        for child in ast.walk(node):
            resolved = self.scope.resolve(child)
            if resolved == "typing.Any":
                self.finding("ANY001", child)
            if resolved == "builtins.object":
                self.finding("OBJ001", child)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.annotation(node.annotation)
        if self.scope.resolve(node.annotation) == "typing.TypeAlias" and node.value:
            self.annotation(node.value)
        super().visit_AnnAssign(node)

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.owners.append(node.name)
        super()._function(node)
        self.owners.pop()

    def visit_annotation(self, node: ast.expr) -> None:
        self.annotation(node)
        super().visit_annotation(node)

    def visit_Call(self, node: ast.Call) -> None:
        resolved = self.scope.resolve(node.func)
        if resolved == "typing.cast":
            self.finding("CAST001", node)
            if node.args:
                self.annotation(node.args[0])
        if resolved == "contextlib.suppress" and any(
            self.scope.resolve(item) in BROAD for item in node.args
        ):
            self.finding("CATCH001", node)
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        target = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
        if target is not None and self.scope.resolve(target) in GENERIC:
            self.finding("ERR001", node)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        targets = node.type.elts if isinstance(node.type, ast.Tuple) else ()
        targets = targets or ((node.type,) if node.type else ())
        if node.type is None or any(self.scope.resolve(target) in BROAD for target in targets):
            self.finding("CATCH001", node)
        super().visit_ExceptHandler(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.owners.append(node.name)
        decorators = [
            self.scope.resolve(item.func if isinstance(item, ast.Call) else item)
            for item in node.decorator_list
        ]
        frozen = any(
            isinstance(item, ast.Call)
            and self.scope.resolve(item.func) == "dataclasses.dataclass"
            and any(
                key.arg == "frozen"
                and isinstance(key.value, ast.Constant)
                and key.value.value is True
                for key in item.keywords
            )
            for item in node.decorator_list
        )
        if "dataclasses.dataclass" in decorators and not frozen:
            self.finding("DATA001", node)
        super().visit_ClassDef(node)
        self.owners.pop()

    def visit_If(self, node: ast.If) -> None:
        detail = equality_chain(node)
        if detail and id(node) not in self.var_children:
            self.finding("VAR001", node, detail)
            self.var_children.update(id(item) for item in elif_nodes(node))
        self.visit(node.test)
        for statement in [*node.body, *node.orelse]:
            self.visit(statement)

    def visit_Import(self, node: ast.Import) -> None:
        self.imports(node)
        super().visit_Import(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.imports(node)
        super().visit_ImportFrom(node)

    def imports(self, node: ast.Import | ast.ImportFrom) -> None:
        package_path = self.relative.startswith("src/openai_tts_gui/") and any(
            f"/{part}/" in self.relative for part in ("core", "tts", "keystore", "presets")
        )
        config_path = self.relative in {
            "src/openai_tts_gui/config/settings.py",
            "src/openai_tts_gui/config/app_settings.py",
        }
        bridge = False
        for target in import_targets(node, self.module):
            if (package_path or config_path) and target.startswith("PyQt6"):
                self.finding("QT001", node)
            bridge = (
                self.module == "openai_tts_gui.tts._compat"
                and target == "openai_tts_gui.gui.TTSWorker"
            )
            lazy = (
                self.module == "openai_tts_gui.tts.__init__"
                and target == "openai_tts_gui.tts._compat.TTSProcessor"
                and node.lineno in self.lazy_imports
            )
            tts_gui = self.module.startswith("openai_tts_gui.tts") and target.startswith(
                "openai_tts_gui.gui"
            )
            invalid_compat = target.startswith("openai_tts_gui.tts._compat") and not lazy
            if (tts_gui and not bridge) or invalid_compat:
                self.finding("QTBRIDGE001", node)
        for target in self.imported_modules(node):
            parts, origin = target.split("."), self.module.split(".")
            if (
                len(parts) > 2
                and parts[:1] == ["openai_tts_gui"]
                and len(origin) > 1
                and parts[1] != origin[1]
                and not bridge
            ):
                self.finding("IMP001", node)

    def imported_modules(self, node: ast.Import | ast.ImportFrom) -> tuple[str, ...]:
        if isinstance(node, ast.Import):
            return tuple(item.name for item in node.names)
        base = import_target(node, self.module)
        candidates = tuple(
            f"{base}.{item.name}"
            for item in node.names
            if f"{base}.{item.name}" in self.module_inventory
        )
        if candidates:
            return tuple(dict.fromkeys(candidates))
        return (base,) if base in self.module_inventory else ()


def lazy_lines(tree: ast.Module) -> set[int]:
    return {
        item.lineno
        for function in tree.body
        if isinstance(function, ast.FunctionDef)
        and function.name == "__getattr__"
        and [argument.arg for argument in function.args.args] == ["name"]
        for statement in function.body
        if isinstance(statement, ast.If)
        and processor_condition(statement.test)
        and processor_branch(statement)
        for item in statement.body
        if isinstance(item, ast.ImportFrom) and processor_import(item)
    }


def processor_condition(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Name)
        and node.left.id == "name"
        and len(node.ops) == len(node.comparators) == 1
        and isinstance(node.ops[0], ast.Eq)
        and isinstance(node.comparators[0], ast.Constant)
        and node.comparators[0].value == "TTSProcessor"
    )


def processor_import(node: ast.ImportFrom) -> bool:
    return (
        node.level == 1
        and node.module == "_compat"
        and [item.name for item in node.names] == ["TTSProcessor"]
    )


def processor_branch(node: ast.If) -> bool:
    has_import = any(
        processor_import(item) for item in node.body if isinstance(item, ast.ImportFrom)
    )
    has_projection = any(
        isinstance(item, ast.Return)
        and isinstance(item.value, ast.Name)
        and item.value.id == "TTSProcessor"
        for item in node.body
    )
    return has_import and has_projection


def elif_nodes(node: ast.If) -> tuple[ast.If, ...]:
    nodes: list[ast.If] = []
    current = node
    while len(current.orelse) == 1 and isinstance(current.orelse[0], ast.If):
        current = current.orelse[0]
        nodes.append(current)
    return tuple(nodes)
