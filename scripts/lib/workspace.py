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
