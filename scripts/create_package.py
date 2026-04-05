#!/usr/bin/env python3
"""Create a new package in the Spakky workspace.

This script scaffolds a new core package or plugin package with all the
necessary files and configuration:
- pyproject.toml with proper dependencies
- README.md
- CHANGELOG.md
- src/ directory structure
- tests/ directory
- .pre-commit-config.yaml
- .vscode/settings.json

Usage:
    uv run python scripts/create_package.py core my-package
    uv run python scripts/create_package.py plugin my-plugin
    uv run python scripts/create_package.py plugin my-plugin --description "My plugin description"
"""

from __future__ import annotations

import re
import tomllib
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel
from rich.tree import Tree

from common import (
    WORKSPACE_ROOT,
    ScriptError,
    console,
    get_all_packages,
    print_error,
    print_header,
    print_info,
    print_success,
    print_warning,
    run_command,
)

app = typer.Typer(
    help="Create a new package in the Spakky workspace.",
    no_args_is_help=True,
)


class PackageType(str, Enum):
    """Type of package to create."""

    CORE = "core"
    PLUGIN = "plugin"


# -----------------------------------------------------------------------------
# Error Classes
# -----------------------------------------------------------------------------


class PackageExistsError(ScriptError):
    """Raised when a package already exists."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.message = f"Package '{name}' already exists."
        super().__init__()


class InvalidPackageNameError(ScriptError):
    """Raised when a package name is invalid."""

    def __init__(self, name: str, reason: str) -> None:
        self.name = name
        self.reason = reason
        self.message = f"Invalid package name '{name}': {reason}"
        super().__init__()


# -----------------------------------------------------------------------------
# Version Helpers
# -----------------------------------------------------------------------------


def get_current_version() -> str:
    """Get the current workspace version from pyproject.toml.

    Returns:
        Current version string.
    """
    pyproject_path = WORKSPACE_ROOT / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        config = tomllib.load(f)
    return config.get("project", {}).get("version", "0.0.1")


# -----------------------------------------------------------------------------
# Template Functions
# -----------------------------------------------------------------------------


def generate_pyproject_toml(
    name: str,
    pkg_type: PackageType,
    description: str,
    version: str,
) -> str:
    """Generate pyproject.toml content for a new package.

    Args:
        name: Package name (e.g., 'spakky-mypackage').
        pkg_type: Type of package (core or plugin).
        description: Package description.
        version: Package version.

    Returns:
        pyproject.toml content as string.
    """
    # Determine module structure
    if pkg_type == PackageType.CORE:
        # Core packages: spakky.mypackage
        module_suffix = name.replace("spakky-", "").replace("-", "_")
        module_name = f"spakky.{module_suffix}"
        pythonpath = f"src/spakky/{module_suffix}"
    else:
        # Plugin packages: spakky.plugins.mypackage
        module_suffix = name.replace("spakky-", "").replace("-", "_")
        module_name = f"spakky.plugins.{module_suffix}"
        pythonpath = f"src/spakky/plugins/{module_suffix}"

    return f'''[project]
name = "{name}"
version = "{version}"
description = "{description}"
readme = "README.md"
requires-python = ">=3.11"
license = {{ text = "MIT" }}
authors = [{{ name = "Spakky", email = "sejong418@icloud.com" }}]
dependencies = ["spakky>={version}"]

[project.entry-points."spakky.plugins"]
{name} = "{module_name}.main:initialize"

[build-system]
requires = ["uv_build>=0.10.10,<0.11.0"]
build-backend = "uv_build"

[tool.uv.build-backend]
module-root = "src"
module-name = "{module_name}"

[tool.pyrefly]
python-version = "3.14"
search_path = ["src", "."]
project_excludes = ["**/__pycache__", "**/*.pyc"]

[tool.ruff]
builtins = ["_"]
cache-dir = "~/.cache/ruff"

[tool.pytest.ini_options]
pythonpath = "{pythonpath}"
testpaths = "tests"
python_files = ["test_*.py"]
asyncio_mode = "auto"
addopts = """
    --cov
    --cov-report=term
    --cov-report=xml
    --no-cov-on-fail
    --strict-markers
    --dist=load
    -p no:warnings
    -n auto
    --spec
"""
spec_test_format = "{{result}} {{docstring_summary}}"

[tool.coverage.run]
include = ["{pythonpath}/**/*.py"]
branch = true

[tool.coverage.report]
show_missing = true
precision = 2
fail_under = 90
skip_empty = true
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "@(abc\\\\.)?abstractmethod",
    "@(typing\\\\.)?overload",
    "\\\\.\\\\.\\\\.",
    "pass",
]

[tool.uv.sources]
spakky = {{ workspace = true }}
'''


def generate_precommit_config(name: str, pkg_type: PackageType) -> str:
    """Generate .pre-commit-config.yaml content.

    Args:
        name: Package name.
        pkg_type: Type of package (core or plugin).

    Returns:
        .pre-commit-config.yaml content as string.
    """
    if pkg_type == PackageType.CORE:
        package_dir = f"core/{name}"
    else:
        package_dir = f"plugins/{name}"

    return f'''repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: trailing-whitespace
      - id: check-yaml
        args: ['--unsafe']
      - id: check-json
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.15.5
    hooks:
      - id: ruff
        types_or: [python, pyi]
        args: [--fix]
      - id: ruff-format
        types_or: [python, pyi]
  - repo: local
    hooks:
      - id: pyrefly-typecheck
        name: Pyrefly (type checking)
        entry: bash -c 'if [ -d "{package_dir}" ]; then cd {package_dir}; fi && uv run pyrefly check --disable-project-excludes-heuristics'
        language: system
        types: [python]
        pass_filenames: false
        always_run: true

      - id: pytest
        name: Run pytest
        entry: bash -c 'if [ -d "{package_dir}" ]; then cd {package_dir}; fi && uv run pytest'
        language: system
        types: [python]
        pass_filenames: false
        always_run: true
        stages: [pre-push]
'''


def generate_vscode_settings(pkg_type: PackageType) -> str:
    """Generate .vscode/settings.json content.

    Args:
        pkg_type: Type of package (core or plugin).

    Returns:
        settings.json content as string.
    """
    # Both core and plugin have the same depth from root
    return """{
\t"python.defaultInterpreterPath": "${workspaceFolder}/../../.venv/bin/python",
\t"python.testing.cwd": "${workspaceFolder}",
\t"python.testing.pytestArgs": ["--no-cov"],
\t"python-envs.pythonProjects": [
\t\t{
\t\t\t"path": ".",
\t\t\t"envManager": "ms-python.python:venv",
\t\t\t"packageManager": "ms-python.python:pip"
\t\t}
\t]
}
"""


def generate_readme(name: str, description: str) -> str:
    """Generate README.md content.

    Args:
        name: Package name.
        description: Package description.

    Returns:
        README.md content as string.
    """
    return f"""# {name}

{description}

## Installation

```bash
pip install {name}
```

## Usage

```python
# TODO: Add usage examples
```

## License

MIT License
"""


def generate_changelog(name: str, version: str) -> str:
    """Generate CHANGELOG.md content.

    Args:
        name: Package name.
        version: Initial version.

    Returns:
        CHANGELOG.md content as string.
    """
    return f"""# Changelog

All notable changes to {name} are documented in this file.

See the root CHANGELOG.md for a full summary of modifications affecting the
entire workspace.

## {version}

- Initial release
"""


def generate_main_py(name: str, pkg_type: PackageType) -> str:
    """Generate main.py (plugin entry point) content.

    Args:
        name: Package name.
        pkg_type: Type of package.

    Returns:
        main.py content as string.
    """
    return '''"""Plugin initialization entry point."""

from spakky.core.application.application import SpakkyApplication


def initialize(app: SpakkyApplication) -> None:
    """Initialize the plugin.

    Args:
        app: The SpakkyApplication instance.
    """
    # TODO: Implement plugin initialization
    pass
'''


def generate_init_py() -> str:
    """Generate __init__.py content.

    Returns:
        __init__.py content as string.
    """
    return '"""Package module."""\n'


def generate_test_init_py() -> str:
    """Generate tests/__init__.py content.

    Returns:
        tests/__init__.py content as string.
    """
    return '"""Test suite."""\n'


# -----------------------------------------------------------------------------
# Package Creation
# -----------------------------------------------------------------------------


def validate_package_name(name: str) -> None:
    """Validate package name.

    Args:
        name: Package name to validate.

    Raises:
        InvalidPackageNameError: If name is invalid.
    """
    if not name:
        raise InvalidPackageNameError(name, "Name cannot be empty")

    if not re.match(r"^[a-z][a-z0-9-]*$", name):
        raise InvalidPackageNameError(
            name,
            "Name must start with lowercase letter and contain only lowercase letters, numbers, and hyphens",
        )

    if not name.startswith("spakky-"):
        raise InvalidPackageNameError(name, "Name must start with 'spakky-'")

    # Check if package already exists
    existing_names = {pkg.name for pkg in get_all_packages()}
    if name in existing_names:
        raise PackageExistsError(name)


def update_workspace_members(package_path: str) -> None:
    """Add the new package to workspace members in root pyproject.toml.

    Args:
        package_path: Relative path to the new package.
    """
    pyproject_path = WORKSPACE_ROOT / "pyproject.toml"
    content = pyproject_path.read_text()

    # Find the members array and add the new package
    # Pattern matches the members array
    pattern = r"(\[tool\.uv\.workspace\]\nmembers = \[)(.*?)(\])"

    def add_member(match: re.Match[str]) -> str:
        prefix = match.group(1)
        members = match.group(2)
        suffix = match.group(3)

        # Parse existing members
        existing = [
            m.strip().strip('"').strip("'") for m in members.split(",") if m.strip()
        ]

        # Add new member
        if package_path not in existing:
            existing.append(package_path)

        # Format members
        formatted = ",\n  ".join(f'"{m}"' for m in existing)
        return f"{prefix}\n  {formatted},\n{suffix}"

    new_content = re.sub(pattern, add_member, content, flags=re.DOTALL)
    pyproject_path.write_text(new_content)


def update_version_files(package_path: str) -> None:
    """Add the new package to commitizen version_files in root pyproject.toml.

    Args:
        package_path: Relative path to the new package (e.g., "plugins/spakky-celery").
    """
    pyproject_path = WORKSPACE_ROOT / "pyproject.toml"
    content = pyproject_path.read_text()

    version_entry = f"{package_path}/pyproject.toml:version"

    # Find the version_files array and add the new entry
    pattern = r"(version_files = \[)(.*?)(\])"

    def add_version_file(match: re.Match[str]) -> str:
        prefix = match.group(1)
        entries = match.group(2)
        suffix = match.group(3)

        # Parse existing entries
        existing = [
            e.strip().strip('"').strip("'") for e in entries.split(",") if e.strip()
        ]

        # Add new entry if not exists
        if version_entry not in existing:
            existing.append(version_entry)

        # Format entries
        formatted = ",\n  ".join(f'"{e}"' for e in existing)
        return f"{prefix}\n  {formatted},\n{suffix}"

    new_content = re.sub(pattern, add_version_file, content, flags=re.DOTALL)
    pyproject_path.write_text(new_content)


def update_uv_sources(name: str) -> None:
    """Add the new package to uv sources in root pyproject.toml.

    Args:
        name: Package name (e.g., "spakky-celery").
    """
    pyproject_path = WORKSPACE_ROOT / "pyproject.toml"
    content = pyproject_path.read_text()

    source_entry = f"{name} = {{ workspace = true }}"

    # Find [tool.uv.sources] section and add entry before the next section or EOF
    pattern = r"(\[tool\.uv\.sources\]\n)(.*?)(\n\[|\Z)"

    def add_source(match: re.Match[str]) -> str:
        header = match.group(1)
        entries = match.group(2)
        next_section = match.group(3)

        # Parse existing entries as lines
        lines = [line for line in entries.strip().split("\n") if line.strip()]

        # Check if entry already exists
        entry_key = f"{name} ="
        if not any(line.strip().startswith(entry_key) for line in lines):
            lines.append(source_entry)

        formatted = "\n".join(lines)
        return f"{header}{formatted}\n{next_section}"

    new_content = re.sub(pattern, add_source, content, flags=re.DOTALL)
    pyproject_path.write_text(new_content)


def create_package_structure(
    name: str,
    pkg_type: PackageType,
    description: str,
) -> Path:
    """Create the package directory structure and files.

    Args:
        name: Package name.
        pkg_type: Type of package.
        description: Package description.

    Returns:
        Path to the created package directory.
    """
    version = get_current_version()

    # Determine base directory
    if pkg_type == PackageType.CORE:
        base_dir = WORKSPACE_ROOT / "core" / name
        module_suffix = name.replace("spakky-", "").replace("-", "_")
        src_path = base_dir / "src" / "spakky" / module_suffix
    else:
        base_dir = WORKSPACE_ROOT / "plugins" / name
        module_suffix = name.replace("spakky-", "").replace("-", "_")
        src_path = base_dir / "src" / "spakky" / "plugins" / module_suffix

    # Create directories
    base_dir.mkdir(parents=True, exist_ok=True)
    src_path.mkdir(parents=True, exist_ok=True)
    (base_dir / "tests").mkdir(exist_ok=True)
    (base_dir / ".vscode").mkdir(exist_ok=True)

    # NOTE: Do NOT create __init__.py in namespace package directories
    # (spakky/, spakky/plugins/) - PEP 420 implicit namespace packages
    init_content = generate_init_py()

    # Module __init__.py
    (src_path / "__init__.py").write_text(init_content)

    # Create main.py (plugin entry point)
    (src_path / "main.py").write_text(generate_main_py(name, pkg_type))

    # Create py.typed marker file (PEP 561)
    (src_path / "py.typed").write_text("")

    # Create tests/__init__.py
    (base_dir / "tests" / "__init__.py").write_text(generate_test_init_py())

    # Create pyproject.toml
    (base_dir / "pyproject.toml").write_text(
        generate_pyproject_toml(name, pkg_type, description, version)
    )

    # Create README.md
    (base_dir / "README.md").write_text(generate_readme(name, description))

    # Create CHANGELOG.md
    (base_dir / "CHANGELOG.md").write_text(generate_changelog(name, version))

    # Create .pre-commit-config.yaml
    (base_dir / ".pre-commit-config.yaml").write_text(
        generate_precommit_config(name, pkg_type)
    )

    # Create .vscode/settings.json
    (base_dir / ".vscode" / "settings.json").write_text(
        generate_vscode_settings(pkg_type)
    )

    return base_dir


def show_package_tree(base_dir: Path) -> None:
    """Display the created package structure as a tree.

    Args:
        base_dir: Path to the package directory.
    """
    tree = Tree(f"[bold blue]{base_dir.name}[/]")

    def add_to_tree(parent: Tree, path: Path, depth: int = 0) -> None:
        """Recursively add directory contents to tree."""
        if depth > 3:  # Limit depth
            return

        items = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
        for item in items:
            if item.name.startswith(".") and item.name not in {
                ".vscode",
                ".pre-commit-config.yaml",
            }:
                continue
            if item.name == "__pycache__":
                continue

            if item.is_dir():
                branch = parent.add(f"[bold cyan]{item.name}/[/]")
                add_to_tree(branch, item, depth + 1)
            else:
                parent.add(f"[green]{item.name}[/]")

    add_to_tree(tree, base_dir)
    console.print(tree)


# -----------------------------------------------------------------------------
# Commands
# -----------------------------------------------------------------------------


@app.command()
def create(
    pkg_type: Annotated[
        PackageType,
        typer.Argument(help="Type of package to create: 'core' or 'plugin'."),
    ],
    name: Annotated[
        str,
        typer.Argument(help="Package name (must start with 'spakky-')."),
    ],
    description: Annotated[
        str,
        typer.Option(
            "--description",
            "-d",
            help="Package description.",
        ),
    ] = "",
    sync: Annotated[
        bool,
        typer.Option(
            "--sync",
            "-s",
            help="Run 'uv sync' after creating the package.",
        ),
    ] = True,
) -> None:
    """Create a new package in the workspace."""
    try:
        print_header(f"Creating {pkg_type.value} package: {name}")

        # Validate name
        validate_package_name(name)

        # Set default description
        if not description:
            if pkg_type == PackageType.CORE:
                description = "Core module for Spakky Framework"
            else:
                description = "Plugin for Spakky Framework"

        # Create package structure
        print_info("Creating package structure...")
        base_dir = create_package_structure(name, pkg_type, description)

        # Update workspace members
        print_info("Updating workspace configuration...")
        if pkg_type == PackageType.CORE:
            package_path = f"core/{name}"
        else:
            package_path = f"plugins/{name}"
        update_workspace_members(package_path)
        update_version_files(package_path)
        update_uv_sources(name)

        # Show created structure
        console.print()
        console.print("[bold]Created package structure:[/]")
        show_package_tree(base_dir)

        # Sync dependencies
        if sync:
            console.print()
            print_info("Running uv sync...")
            try:
                run_command(
                    ["uv", "sync", "--all-packages", "--all-extras"],
                    cwd=WORKSPACE_ROOT,
                    capture=False,
                )
            except ScriptError as e:
                print_warning(f"uv sync failed: {e}")
                print_info(
                    "You may need to run 'uv sync --all-packages --all-extras' manually"
                )

        console.print()
        print_success(f"Package '{name}' created successfully!")

        # Show next steps
        console.print()
        console.print(
            Panel(
                f"""[bold]Next steps:[/]

1. Navigate to the package directory:
   [cyan]cd {package_path}[/]

2. Implement your code in:
   [cyan]src/spakky/{"/plugins/" if pkg_type == PackageType.PLUGIN else ""}{name.replace("spakky-", "").replace("-", "_")}/[/]

3. Add tests in:
   [cyan]tests/[/]

4. Run tests:
   [cyan]uv run pytest[/]
""",
                title="🚀 Getting Started",
                border_style="green",
            )
        )

    except (PackageExistsError, InvalidPackageNameError) as e:
        print_error(str(e))
        raise typer.Exit(1) from e
    except ScriptError as e:
        print_error(str(e))
        raise typer.Exit(1) from e


if __name__ == "__main__":
    app()
