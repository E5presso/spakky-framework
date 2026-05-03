"""Validate Python harness rules that type checkers cannot enforce."""

from __future__ import annotations

import ast
from pathlib import Path
import sys


class HarnessViolation:
    def __init__(self, path: Path, line: int, message: str) -> None:
        self.path = path
        self.line = line
        self.message = message

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


class PythonHarnessVisitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.violations: list[HarnessViolation] = []

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module in {"typing", "typing_extensions"}:
            for alias in node.names:
                if alias.name == "Protocol":
                    self._add(
                        node.lineno,
                        "Protocol import is forbidden; use ABC with explicit inheritance",
                    )
                if alias.name == "runtime_checkable":
                    self._add(
                        node.lineno,
                        "runtime_checkable is forbidden; use ABC with explicit inheritance",
                    )
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if self._inherits_protocol(node):
            self._add(
                node.lineno,
                "Protocol inheritance is forbidden; use ABC with explicit inheritance",
            )
        if self._uses_runtime_checkable(node):
            self._add(node.lineno, "runtime_checkable structural typing is forbidden")
        if node.name.startswith("Abstract") and self._is_pure_abstract_contract(node):
            self._add(
                node.lineno,
                "pure abstract contract uses Abstract prefix; use I* interface naming",
            )
        self.generic_visit(node)

    def _inherits_protocol(self, node: ast.ClassDef) -> bool:
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id == "Protocol":
                return True
            if isinstance(base, ast.Attribute) and base.attr == "Protocol":
                return True
        return False

    def _uses_runtime_checkable(self, node: ast.ClassDef) -> bool:
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name) and decorator.id == "runtime_checkable":
                return True
            if (
                isinstance(decorator, ast.Attribute)
                and decorator.attr == "runtime_checkable"
            ):
                return True
        return False

    def _is_pure_abstract_contract(self, node: ast.ClassDef) -> bool:
        methods: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
        for child in node.body:
            if self._is_docstring(child):
                continue
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(child)
                continue
            return False
        return bool(methods) and all(
            self._is_abstract_method(method) for method in methods
        )

    def _is_docstring(self, node: ast.stmt) -> bool:
        return (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        )

    def _is_abstract_method(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name) and decorator.id == "abstractmethod":
                return True
            if (
                isinstance(decorator, ast.Attribute)
                and decorator.attr == "abstractmethod"
            ):
                return True
        return False

    def _add(self, line: int, message: str) -> None:
        self.violations.append(HarnessViolation(self.path, line, message))


def iter_python_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix == ".py" else []
    return sorted(
        path
        for path in root.rglob("*.py")
        if ".venv" not in path.parts and "__pycache__" not in path.parts
    )


def validate(paths: list[Path]) -> list[HarnessViolation]:
    violations: list[HarnessViolation] = []
    for root in paths:
        for path in iter_python_files(root):
            visitor = PythonHarnessVisitor(path)
            visitor.visit(ast.parse(path.read_text(), filename=str(path)))
            violations.extend(visitor.violations)
    return violations


def main() -> int:
    paths = [Path(arg) for arg in sys.argv[1:]] or [Path(".")]
    violations = validate(paths)
    if violations:
        print("Python harness violations:")
        for violation in violations:
            print(violation.render())
        return 1
    print("Python harness validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
