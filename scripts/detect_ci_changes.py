#!/usr/bin/env python3
"""Detect changed packages in the monorepo for CI matrix generation.

This script analyzes git changes and outputs a JSON list of package names
that need to be tested. It handles workspace member detection and
cascading changes (e.g., core changes trigger all package tests).

Usage:
    python scripts/detect_ci_changes.py [base_ref] [head_ref]

Example:
    python scripts/detect_ci_changes.py origin/main HEAD
    # Output: ["spakky", "spakky-fastapi"]
"""

import json
import subprocess
import sys
import tomllib
from pathlib import Path


def get_workspace_packages() -> dict[str, str]:
    """Read workspace members and resolve to package names.

    Returns:
        A dictionary mapping directory paths to package names.
        Example: {"spakky": "spakky", "plugins/spakky-fastapi": "spakky-fastapi"}
    """
    root_dir = Path(__file__).parent.parent
    pyproject_path = root_dir / "pyproject.toml"

    try:
        with open(pyproject_path, "rb") as f:
            pyproject = tomllib.load(f)

        members = (
            pyproject.get("tool", {})
            .get("uv", {})
            .get("workspace", {})
            .get("members", [])
        )

        packages: dict[str, str] = {}
        for member in members:
            member_config = root_dir / member / "pyproject.toml"
            try:
                with open(member_config, "rb") as f:
                    pkg_config = tomllib.load(f)
                pkg_name = pkg_config.get("project", {}).get("name", "")
                if pkg_name:
                    packages[member] = pkg_name
            except FileNotFoundError:
                continue

        return packages
    except Exception as e:
        print(f"Error reading pyproject.toml: {e}", file=sys.stderr)
        return {}


def get_changed_files(base_ref: str, head_ref: str) -> set[str]:
    """Get changed files between base and head refs."""
    try:
        # Fetch if needed (in CI usually fetch-depth: 0 is recommended or fetch base)
        # Assuming the refs are available
        cmd = ["git", "diff", "--name-only", f"{base_ref}...{head_ref}"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if result.returncode != 0:
            # Try 2 dots if 3 dots fail (e.g. local branch)
            cmd = ["git", "diff", "--name-only", f"{base_ref}..{head_ref}"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if result.returncode != 0:
            # Fallback to HEAD comparison if refs fail
            cmd = ["git", "diff", "--name-only", "HEAD"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        return (
            set(result.stdout.strip().split("\n")) if result.stdout.strip() else set()
        )
    except Exception as e:
        print(f"Error getting changed files: {e}", file=sys.stderr)
        return set()


def main():
    base_ref = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    head_ref = sys.argv[2] if len(sys.argv) > 2 else "HEAD"

    packages = get_workspace_packages()  # {path: name}
    changed_files = get_changed_files(base_ref, head_ref)

    changed_packages: set[str] = set()

    # Check for changes in each member directory
    for path, name in packages.items():
        if any(f.startswith(f"{path}/") for f in changed_files):
            changed_packages.add(name)

    # If core framework (spakky) changes, test everything
    if "spakky" in changed_packages:
        changed_packages = set(packages.values())

    # If pyproject.toml or uv.lock changes, test everything
    if "pyproject.toml" in changed_files or "uv.lock" in changed_files:
        changed_packages = set(packages.values())

    # Output JSON list for GitHub Actions matrix
    print(json.dumps(sorted(changed_packages)))


if __name__ == "__main__":
    main()
