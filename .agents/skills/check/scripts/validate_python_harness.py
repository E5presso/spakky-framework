"""Validate Python harness rules that type checkers cannot enforce."""

from __future__ import annotations

import ast
from pathlib import Path
import sys
import tomllib

BUILTIN_EXCEPTIONS = {
    "TypeError",
    "ValueError",
}

INFRASTRUCTURE_IMPORT_ROOTS = {
    "spakky.data",
    "spakky.event",
    "spakky.outbox",
    "spakky.plugins",
    "spakky.task",
    "spakky.tracing",
}

OPT_OUT_MARKERS = (
    "# type: ignore",
    "# pyrefly: ignore",
    "# pragma: no cover",
    "# pragma: no branch",
)


class HarnessViolation:
    def __init__(self, path: Path, line: int, message: str) -> None:
        self.path = path
        self.line = line
        self.message = message

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


class PythonHarnessVisitor(ast.NodeVisitor):
    def __init__(self, path: Path, workspace_root: Path) -> None:
        self.path = path
        self.workspace_root = workspace_root
        self.violations: list[HarnessViolation] = []

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self._check_import(node.module, node.lineno)
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

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._check_import(alias.name, node.lineno)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if self._is_test_file() and node.name.startswith("Test"):
            self._add(
                node.lineno, "class-based tests are forbidden; use function tests"
            )
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

    def visit_Raise(self, node: ast.Raise) -> None:
        if self._is_src_file() and self._raises_builtin_exception(node):
            self._add(
                node.lineno,
                "raising built-in exceptions in src is forbidden; use framework errors",
            )
        self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert) -> None:
        if self._is_src_file():
            self._add(node.lineno, "assert statements in src are forbidden")
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self._is_src_file() and node.name == "__str__" and self._is_error_file():
            self._add(node.lineno, "__str__ overrides in src are forbidden")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if self._is_src_file() and self._is_dynamic_attr_call(node):
            if not self._node_has_reason(node):
                self._add(
                    node.lineno,
                    "dynamic attribute access requires an inline reason comment",
                )
        self.generic_visit(node)

    def _check_import(self, module: str | None, line: int) -> None:
        if module is None:
            return
        if self._is_plugin_src_file() and module.startswith("spakky.plugins."):
            own_plugin = self._own_plugin_module()
            if own_plugin is not None and not module.startswith(own_plugin):
                self._add(line, "plugins must not directly import other plugins")
        if self._is_domain_src_file():
            for root in INFRASTRUCTURE_IMPORT_ROOTS:
                if module == root or module.startswith(f"{root}."):
                    self._add(
                        line,
                        "domain layer must not import infrastructure packages",
                    )

    def _inherits_protocol(self, node: ast.ClassDef) -> bool:
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id == "Protocol":
                return True
            if isinstance(base, ast.Attribute) and base.attr == "Protocol":
                return True
        return False

    def _raises_builtin_exception(self, node: ast.Raise) -> bool:
        exc = node.exc
        if exc is None:
            return False
        if isinstance(exc, ast.Name):
            return exc.id in BUILTIN_EXCEPTIONS
        if isinstance(exc, ast.Call):
            func = exc.func
            return isinstance(func, ast.Name) and func.id in BUILTIN_EXCEPTIONS
        return False

    def _is_dynamic_attr_call(self, node: ast.Call) -> bool:
        return isinstance(node.func, ast.Name) and node.func.id in {
            "getattr",
            "hasattr",
            "setattr",
        }

    def _node_has_reason(self, node: ast.Call) -> bool:
        end_line = node.end_lineno or node.lineno
        for line in range(node.lineno, end_line + 1):
            text = self._line(line)
            if "#" in text and text.split("#", 1)[1].strip():
                return True
        return False

    def _line(self, line: int) -> str:
        return self.path.read_text().splitlines()[line - 1]

    def _is_src_file(self) -> bool:
        return "src" in self._relative_parts()

    def _is_test_file(self) -> bool:
        return "tests" in self._relative_parts()

    def _is_error_file(self) -> bool:
        return self.path.name == "error.py"

    def _is_domain_src_file(self) -> bool:
        parts = self._relative_parts()
        return parts[:3] == ("core", "spakky-domain", "src")

    def _is_plugin_src_file(self) -> bool:
        parts = self._relative_parts()
        return len(parts) >= 3 and parts[0] == "plugins" and parts[2] == "src"

    def _own_plugin_module(self) -> str | None:
        parts = self._relative_parts()
        if len(parts) < 2 or parts[0] != "plugins":
            return None
        plugin_name = parts[1].removeprefix("spakky-").replace("-", "_")
        return f"spakky.plugins.{plugin_name}"

    def _relative_parts(self) -> tuple[str, ...]:
        return self.path.relative_to(self.workspace_root).parts

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
    workspace_root = find_workspace_root(Path.cwd().resolve())
    violations.extend(validate_packaging_metadata(workspace_root))
    for root in paths:
        for path in iter_python_files(root):
            resolved_path = path.resolve()
            visitor = PythonHarnessVisitor(resolved_path, workspace_root)
            source = resolved_path.read_text()
            if resolved_path.name != "validate_python_harness.py":
                for line_number, line in enumerate(source.splitlines(), start=1):
                    marker = next(
                        (item for item in OPT_OUT_MARKERS if item in line),
                        None,
                    )
                    if marker is None:
                        continue
                    suffix = line.split(marker, 1)[1].strip()
                    if suffix.startswith("["):
                        suffix = suffix.split("]", 1)[1].strip()
                    has_reason = (
                        suffix.startswith("- ")
                        or suffix.startswith("— ")
                        or suffix.startswith("# ")
                    )
                    if not has_reason:
                        violations.append(
                            HarnessViolation(
                                resolved_path,
                                line_number,
                                "opt-out comments require an inline reason after ' - '",
                            )
                        )
            visitor.visit(ast.parse(source, filename=str(resolved_path)))
            violations.extend(visitor.violations)
    return violations


def validate_packaging_metadata(workspace_root: Path) -> list[HarnessViolation]:
    core_pyproject = workspace_root / "core" / "spakky" / "pyproject.toml"
    plugins_root = workspace_root / "plugins"
    if not core_pyproject.exists() or not plugins_root.exists():
        return []

    core_metadata = load_toml(core_pyproject)
    project_metadata = table(core_metadata.get("project"))
    optional_dependencies = dependency_table(
        project_metadata.get("optional-dependencies")
    )
    plugin_packages = sorted(
        path.name
        for path in plugins_root.iterdir()
        if path.is_dir()
        and path.name.startswith("spakky-")
        and (path / "pyproject.toml").exists()
    )
    violations: list[HarnessViolation] = []

    for package_name in plugin_packages:
        extra_name = package_name.removeprefix("spakky-")
        dependencies = optional_dependencies.get(extra_name)
        if dependencies is None:
            violations.append(
                HarnessViolation(
                    core_pyproject,
                    1,
                    f"spakky core extras must expose plugin '{extra_name}'",
                )
            )
            continue
        if package_name not in {requirement_name(item) for item in dependencies}:
            violations.append(
                HarnessViolation(
                    core_pyproject,
                    1,
                    f"spakky core extra '{extra_name}' must depend on {package_name}",
                )
            )

    plugin_package_set = set(plugin_packages)
    for extra_name, dependencies in optional_dependencies.items():
        for dependency in dependencies:
            package_name = requirement_name(dependency)
            if package_name in plugin_package_set:
                expected_extra = package_name.removeprefix("spakky-")
                if extra_name != expected_extra:
                    violations.append(
                        HarnessViolation(
                            core_pyproject,
                            1,
                            f"spakky core extra '{extra_name}' points to plugin {package_name}; use extra '{expected_extra}'",
                        )
                    )

    return violations


def load_toml(path: Path) -> dict[str, object]:
    return tomllib.loads(path.read_text())


def table(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, object] = {}
    for key, item in value.items():
        if isinstance(key, str):
            result[key] = item
    return result


def dependency_table(value: object) -> dict[str, list[object]]:
    raw_table = table(value)
    result: dict[str, list[object]] = {}
    for key, item in raw_table.items():
        if isinstance(item, list):
            result[key] = item
    return result


def requirement_name(requirement: object) -> str:
    if not isinstance(requirement, str):
        return ""
    for separator in ("[", "<", ">", "=", "!", "~", ";"):
        requirement = requirement.split(separator, 1)[0]
    return requirement.strip()


def find_workspace_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").exists() and (
            candidate / ".agents" / "skills"
        ).exists():
            return candidate
    return start


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
