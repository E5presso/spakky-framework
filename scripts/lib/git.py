"""Git operations for Spakky workspace scripts."""

from __future__ import annotations

import subprocess

from lib.config import WORKSPACE_ROOT
from lib.models import PackageInfo
from lib.workspace import get_all_packages


def get_staged_files() -> set[str]:
    """Get list of files staged for commit.

    Returns:
        Set of file paths relative to workspace root.
    """
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True,
        text=True,
        cwd=WORKSPACE_ROOT,
        check=False,
    )

    if result.returncode != 0:
        return set()

    return set(result.stdout.strip().split("\n")) if result.stdout.strip() else set()


def get_upstream_branch() -> str:
    """Get the upstream branch for the current branch.

    Returns:
        Upstream branch name, or 'origin/HEAD' as fallback.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "@{upstream}"],
        capture_output=True,
        text=True,
        cwd=WORKSPACE_ROOT,
        check=False,
    )

    if result.returncode != 0:
        return "origin/HEAD"

    return result.stdout.strip()


def get_files_to_push() -> set[str]:
    """Get files changed in commits that will be pushed.

    Returns:
        Set of file paths relative to workspace root.
    """
    upstream = get_upstream_branch()

    result = subprocess.run(
        ["git", "diff", "--name-only", f"{upstream}..HEAD"],
        capture_output=True,
        text=True,
        cwd=WORKSPACE_ROOT,
        check=False,
    )

    if result.returncode != 0:
        # Fallback: get all staged + unstaged changes
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            cwd=WORKSPACE_ROOT,
            check=False,
        )

    return set(result.stdout.strip().split("\n")) if result.stdout.strip() else set()


def get_changed_files_between(base_ref: str, head_ref: str) -> set[str]:
    """Get changed files between two git refs.

    Args:
        base_ref: Base git reference.
        head_ref: Head git reference.

    Returns:
        Set of file paths relative to workspace root.
    """
    # Try 3 dots first (merge base comparison)
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...{head_ref}"],
        capture_output=True,
        text=True,
        cwd=WORKSPACE_ROOT,
        check=False,
    )

    if result.returncode != 0:
        # Try 2 dots (direct comparison)
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base_ref}..{head_ref}"],
            capture_output=True,
            text=True,
            cwd=WORKSPACE_ROOT,
            check=False,
        )

    if result.returncode != 0:
        # Final fallback
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            cwd=WORKSPACE_ROOT,
            check=False,
        )

    return set(result.stdout.strip().split("\n")) if result.stdout.strip() else set()


def get_changed_packages(changed_files: set[str]) -> list[PackageInfo]:
    """Determine which packages have changes based on changed files.

    Args:
        changed_files: Set of changed file paths.

    Returns:
        List of PackageInfo for packages with changes.
    """
    changed_packages: list[PackageInfo] = []

    for pkg in get_all_packages():
        path_prefix = str(pkg.path) + "/"
        if any(f.startswith(path_prefix) for f in changed_files):
            changed_packages.append(pkg)

    return changed_packages
