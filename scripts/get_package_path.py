#!/usr/bin/env python3
"""Resolve package name to its directory path in the uv workspace.

This script reads the workspace configuration from the root pyproject.toml
and finds the directory path for a given package name.

Usage:
    python scripts/get_package_path.py <package-name>

Example:
    python scripts/get_package_path.py spakky-fastapi
    # Output: plugins/spakky-fastapi
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path


def get_package_path(
    package_name: str, workspace_root: Path | None = None
) -> str | None:
    """Find the directory path for a package in the uv workspace.

    Args:
        package_name: The name of the package to find (e.g., "spakky-fastapi").
        workspace_root: Root directory containing pyproject.toml. Defaults to cwd.

    Returns:
        The relative path to the package directory, or None if not found.
    """
    if workspace_root is None:
        workspace_root = Path.cwd()

    root_config_path = workspace_root / "pyproject.toml"
    if not root_config_path.exists():
        return None

    with open(root_config_path, "rb") as f:
        config = tomllib.load(f)

    members = (
        config.get("tool", {}).get("uv", {}).get("workspace", {}).get("members", [])
    )

    for member in members:
        member_config_path = workspace_root / member / "pyproject.toml"
        try:
            with open(member_config_path, "rb") as f:
                pkg_config = tomllib.load(f)
            pkg_name = pkg_config.get("project", {}).get("name", "")
            if pkg_name == package_name:
                return member
        except FileNotFoundError:
            continue

    return None


def get_all_packages(workspace_root: Path | None = None) -> dict[str, str]:
    """Get all packages in the workspace.

    Args:
        workspace_root: Root directory containing pyproject.toml. Defaults to cwd.

    Returns:
        A dictionary mapping package names to their directory paths.
    """
    if workspace_root is None:
        workspace_root = Path.cwd()

    root_config_path = workspace_root / "pyproject.toml"
    if not root_config_path.exists():
        return {}

    with open(root_config_path, "rb") as f:
        config = tomllib.load(f)

    members = (
        config.get("tool", {}).get("uv", {}).get("workspace", {}).get("members", [])
    )
    packages: dict[str, str] = {}

    for member in members:
        member_config_path = workspace_root / member / "pyproject.toml"
        try:
            with open(member_config_path, "rb") as f:
                pkg_config = tomllib.load(f)
            pkg_name = pkg_config.get("project", {}).get("name", "")
            if pkg_name:
                packages[pkg_name] = member
        except FileNotFoundError:
            continue

    return packages


def main() -> int:
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python get_package_path.py <package-name>", file=sys.stderr)
        print("\nAvailable packages:", file=sys.stderr)
        for name, path in get_all_packages().items():
            print(f"  {name} -> {path}", file=sys.stderr)
        return 1

    package_name = sys.argv[1]
    path = get_package_path(package_name)

    if path is None:
        print(f"Package '{package_name}' not found in workspace", file=sys.stderr)
        print("\nAvailable packages:", file=sys.stderr)
        for name, pkg_path in get_all_packages().items():
            print(f"  {name} -> {pkg_path}", file=sys.stderr)
        return 1

    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
