"""Workspace and package discovery for Spakky workspace scripts."""

from __future__ import annotations

import tomllib
from pathlib import Path

from lib.config import WORKSPACE_ROOT
from lib.errors import (
    PackageNotFoundError,
    PyprojectNotFoundError,
    WorkspaceMembersNotFoundError,
)
from lib.models import PackageInfo


def get_workspace_members() -> list[str]:
    """Read workspace member paths from root pyproject.toml.

    Returns:
        List of relative paths to workspace members
        (e.g., ['core/spakky', 'plugins/spakky-fastapi']).

    Raises:
        PyprojectNotFoundError: If pyproject.toml is not found.
        WorkspaceMembersNotFoundError: If no workspace members are defined.
    """
    pyproject_path = WORKSPACE_ROOT / "pyproject.toml"

    if not pyproject_path.exists():
        raise PyprojectNotFoundError(pyproject_path)

    with open(pyproject_path, "rb") as f:
        pyproject = tomllib.load(f)

    members = (
        pyproject.get("tool", {}).get("uv", {}).get("workspace", {}).get("members", [])
    )

    if not members:
        raise WorkspaceMembersNotFoundError

    return members


def get_package_info(member_path: str) -> PackageInfo | None:
    """Get package information from a workspace member path.

    Args:
        member_path: Relative path to the package directory.

    Returns:
        PackageInfo instance, or None if package info cannot be determined.
    """
    pyproject_path = WORKSPACE_ROOT / member_path / "pyproject.toml"

    if not pyproject_path.exists():
        return None

    with open(pyproject_path, "rb") as f:
        config = tomllib.load(f)

    name = config.get("project", {}).get("name", "")
    if not name:
        return None

    # Convert package name to Python import name
    # e.g., 'spakky-fastapi' -> 'spakky_fastapi' or use actual module path
    python_name = name.replace("-", "_")

    return PackageInfo(
        name=name,
        path=Path(member_path),
        python_name=python_name,
    )


def get_all_packages() -> list[PackageInfo]:
    """Get information about all packages in the workspace.

    Returns:
        List of PackageInfo instances for all workspace packages.
    """
    packages: list[PackageInfo] = []
    for member in get_workspace_members():
        info = get_package_info(member)
        if info:
            packages.append(info)
    return packages


def get_package_by_name(name: str) -> PackageInfo:
    """Find a package by its name.

    Args:
        name: Package name (e.g., 'spakky-fastapi').

    Returns:
        PackageInfo instance.

    Raises:
        PackageNotFoundError: If package is not found.
    """
    for pkg in get_all_packages():
        if pkg.name == name:
            return pkg
    raise PackageNotFoundError(name)


def get_package_by_path(path: str) -> PackageInfo:
    """Find a package by its path.

    Args:
        path: Relative path to the package directory.

    Returns:
        PackageInfo instance.

    Raises:
        PackageNotFoundError: If package is not found.
    """
    info = get_package_info(path)
    if info is None:
        raise PackageNotFoundError(path)
    return info


def get_package_dependencies(pkg: PackageInfo) -> set[str]:
    """Get the workspace package dependencies for a package.

    Args:
        pkg: PackageInfo instance.

    Returns:
        Set of workspace package names that this package depends on.
    """
    import re

    pyproject_path = WORKSPACE_ROOT / pkg.path / "pyproject.toml"

    if not pyproject_path.exists():
        return set()

    with open(pyproject_path, "rb") as f:
        config = tomllib.load(f)

    deps = config.get("project", {}).get("dependencies", [])
    all_packages = {p.name for p in get_all_packages()}
    workspace_deps: set[str] = set()

    for dep in deps:
        # Parse dependency string: "spakky-data>=5.0.1" -> "spakky-data"
        match = re.match(r"^([a-zA-Z0-9_-]+)", dep)
        if match:
            dep_name = match.group(1)
            if dep_name in all_packages:
                workspace_deps.add(dep_name)

    return workspace_deps


def build_reverse_dependency_graph() -> dict[str, set[str]]:
    """Build a reverse dependency graph for the workspace.

    Returns:
        Dictionary mapping package name to set of packages that depend on it.
        e.g., {"spakky-data": {"spakky-sqlalchemy"}} means spakky-sqlalchemy
        depends on spakky-data.
    """
    packages = get_all_packages()
    reverse_deps: dict[str, set[str]] = {pkg.name: set() for pkg in packages}

    for pkg in packages:
        deps = get_package_dependencies(pkg)
        for dep in deps:
            if dep in reverse_deps:
                reverse_deps[dep].add(pkg.name)

    return reverse_deps


def get_dependent_packages(
    package_names: set[str],
    reverse_deps: dict[str, set[str]] | None = None,
) -> set[str]:
    """Get all packages that depend on the given packages (transitively).

    Args:
        package_names: Set of package names to find dependents for.
        reverse_deps: Pre-computed reverse dependency graph (optional).

    Returns:
        Set of all package names that depend on any of the given packages,
        including the original packages.
    """
    if reverse_deps is None:
        reverse_deps = build_reverse_dependency_graph()

    result = set(package_names)
    to_process = list(package_names)

    while to_process:
        current = to_process.pop()
        dependents = reverse_deps.get(current, set())
        for dep in dependents:
            if dep not in result:
                result.add(dep)
                to_process.append(dep)

    return result
