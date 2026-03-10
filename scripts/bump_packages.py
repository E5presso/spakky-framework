#!/usr/bin/env python3
"""Single-version release helper for the Spakky workspace.

This script coordinates version bumps across every package in the monorepo.
The workflow is:

1. Determine the next semantic version using commitizen at the workspace root.
2. Run ``cz bump`` with ``--files-only`` so no commit or tag is created yet.
3. Align all intra-package dependency constraints (``spakky>=X.Y.Z``) with the
   freshly bumped version.
4. Refresh each package's ``CHANGELOG.md`` with a short release note.
5. Stage the results and create a unified release commit.
6. Optionally create a tag (with ``--tag`` flag for local use).

In CI, the release workflow creates the tag after updating ``uv.lock`` to ensure
the tag points to the final commit.

Outputs are written in the same shape used by the GitHub Actions workflow so the
publish job can build every package in one go.

Usage:
    uv run python scripts/bump_packages.py
    uv run python scripts/bump_packages.py --dry-run
    uv run python scripts/bump_packages.py --tag

Environment::
    GITHUB_OUTPUT: Optional path for writing GitHub Actions step outputs.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tomllib
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from common import (
    WORKSPACE_ROOT,
    CommandError,
    PackageInfo,
    ScriptError,
    console,
    get_all_packages,
    print_error,
    print_header,
    print_info,
    print_success,
    run_command,
)

app = typer.Typer(
    help="Coordinate version bumps across the workspace.",
    no_args_is_help=False,
)


# -----------------------------------------------------------------------------
# Error Classes
# -----------------------------------------------------------------------------


class BumpError(ScriptError):
    """Raised when the release process encounters an unrecoverable error."""

    def __init__(self, details: str) -> None:
        self.details = details
        self.message = f"Bump failed: {details}"
        super().__init__()


class PatternNotFoundError(BumpError):
    """Raised when a regex pattern is not found in a file."""

    def __init__(self, pattern: str, path: Path) -> None:
        self.pattern = pattern
        self.path = path
        super().__init__(f"Pattern '{pattern}' not found in {path}")


# -----------------------------------------------------------------------------
# Package Categorization
# -----------------------------------------------------------------------------


def get_package_dependencies(
    pkg: PackageInfo,
) -> dict[str, list[str] | dict[str, list[str]]]:
    """Read dependencies from a package's pyproject.toml.

    Returns:
        Dictionary with 'dependencies' and 'optional-dependencies' keys.
    """
    pyproject_path = pkg.full_path / "pyproject.toml"

    with open(pyproject_path, "rb") as f:
        config = tomllib.load(f)

    project = config.get("project", {})
    return {
        "dependencies": project.get("dependencies", []),
        "optional-dependencies": project.get("optional-dependencies", {}),
    }


def categorize_packages() -> tuple[list[PackageInfo], list[PackageInfo]]:
    """Categorize packages into core and plugin packages.

    Core packages: Depend on 'spakky' but are NOT in spakky's optional-dependencies
    Plugin packages: Listed in spakky's optional-dependencies

    Returns:
        Tuple of (core_packages, plugin_packages)
    """
    packages = get_all_packages()
    packages_by_name = {pkg.name: pkg for pkg in packages}

    # Find spakky package
    spakky_pkg = packages_by_name.get("spakky")
    if not spakky_pkg:
        return [], []

    # Get spakky's optional dependencies
    spakky_deps = get_package_dependencies(spakky_pkg)
    optional_deps_dict = spakky_deps["optional-dependencies"]

    # Extract plugin package names from optional-dependencies sections
    plugin_names: set[str] = set()
    if isinstance(optional_deps_dict, dict):
        for deps_list in optional_deps_dict.values():
            for dep in deps_list:
                # Parse "spakky-fastapi>=4.0.0" -> "spakky-fastapi"
                pkg_name = (
                    dep.split(">=")[0].split("==")[0].split("[")[0].strip().strip('"')
                )
                plugin_names.add(pkg_name)

    plugin_packages = [
        packages_by_name[name] for name in plugin_names if name in packages_by_name
    ]

    # Core packages are those that depend on spakky but are not plugins
    core_packages: list[PackageInfo] = []
    for pkg in packages:
        if pkg.name == "spakky":
            continue
        if pkg.name in plugin_names:
            continue

        deps = get_package_dependencies(pkg)
        dependencies = deps["dependencies"]
        if isinstance(dependencies, list) and any(
            "spakky" in dep for dep in dependencies
        ):
            core_packages.append(pkg)

    return core_packages, plugin_packages


# -----------------------------------------------------------------------------
# Version Operations
# -----------------------------------------------------------------------------


def get_next_version() -> str | None:
    """Return the next semantic version as determined by commitizen.

    Returns:
        The next version string, or None if no bump is required.

    Raises:
        BumpError: If commitizen fails unexpectedly.
    """
    result = subprocess.run(
        ["uv", "run", "cz", "bump", "--dry-run", "--yes"],
        cwd=WORKSPACE_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    # Exit code 21 means no version bump required
    NO_BUMP_REQUIRED_EXIT_CODE = 21
    if result.returncode == NO_BUMP_REQUIRED_EXIT_CODE:
        return None

    if result.returncode != 0:
        raise BumpError(result.stderr.strip() or result.stdout.strip())

    output = result.stdout + result.stderr
    match = re.search(r"bump: version [\d.]+ → ([\d.]+)", output)
    if not match:
        raise BumpError("Unable to parse new version from commitizen output")

    return match.group(1)


def perform_commitizen_bump(new_version: str) -> None:
    """Run commitizen to update version files and the root changelog.

    Args:
        new_version: The version being bumped to.

    Raises:
        BumpError: If commitizen fails.
    """
    result = subprocess.run(
        ["uv", "run", "cz", "bump", "--yes", "--files-only"],
        cwd=WORKSPACE_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    if result.returncode != 0:
        raise BumpError(result.stderr.strip() or result.stdout.strip())

    print_success(f"Updated workspace version to {new_version} via commitizen")


def replace_pattern(path: Path, pattern: str, replacement: str) -> None:
    """Replace all occurrences of a regex pattern inside a file.

    Args:
        path: Path to the file.
        pattern: Regex pattern to search for.
        replacement: Replacement string.

    Raises:
        PatternNotFoundError: If pattern is not found.
    """
    content = path.read_text()
    new_content, count = re.subn(pattern, replacement, content)
    if count == 0:
        raise PatternNotFoundError(pattern, path)
    path.write_text(new_content)


def sync_dependency_versions(new_version: str) -> None:
    """Align inter-package version constraints with the new release version.

    Args:
        new_version: The version to set for all dependencies.
    """
    print_info("Updating inter-package dependency constraints...")

    packages = get_all_packages()
    packages_by_name = {pkg.name: pkg for pkg in packages}
    core_packages, plugin_packages = categorize_packages()

    # Get spakky package for updating optional dependencies
    spakky_pkg = packages_by_name.get("spakky")
    if spakky_pkg:
        core_pyproject = spakky_pkg.full_path / "pyproject.toml"
        for plugin in plugin_packages:
            try:
                pattern = rf'"{plugin.name}>=([\d.]+)"'
                replacement = f'"{plugin.name}>={new_version}"'
                replace_pattern(core_pyproject, pattern, replacement)
            except PatternNotFoundError:
                pass  # Plugin may not be in optional deps yet

    # Update each package's dependencies with proper version constraints
    for pkg in packages:
        if pkg.name == "spakky":
            continue

        package_pyproject = pkg.full_path / "pyproject.toml"
        deps = get_package_dependencies(pkg)
        dependencies = deps["dependencies"]

        if not isinstance(dependencies, list):
            continue

        for dep in dependencies:
            dep_name = (
                dep.split(">=")[0].split("==")[0].split("[")[0].strip().strip('"')
            )
            if dep_name in packages_by_name:
                try:
                    pattern = rf'"{dep_name}>=([\d.]+)"'
                    replacement = f'"{dep_name}>={new_version}"'
                    replace_pattern(package_pyproject, pattern, replacement)
                except PatternNotFoundError:
                    pass  # Dependency may use different format


# -----------------------------------------------------------------------------
# Changelog Operations
# -----------------------------------------------------------------------------


def write_changelog(pkg: PackageInfo, version: str) -> None:
    """Write a minimal changelog entry for the given package.

    Args:
        pkg: Package information.
        version: The version being released.
    """
    changelog_path = pkg.full_path / "CHANGELOG.md"
    content = f"""# Changelog

All notable changes to {pkg.name} are documented in this file.

See the root CHANGELOG.md for a full summary of modifications affecting the
entire workspace.

## {version}

- Release {version}
"""
    changelog_path.write_text(content)


def refresh_changelogs(version: str) -> None:
    """Regenerate changelog stubs for every package.

    Args:
        version: The version being released.
    """
    print_info("Refreshing package changelog stubs...")
    for pkg in get_all_packages():
        write_changelog(pkg, version)


# -----------------------------------------------------------------------------
# Git Operations
# -----------------------------------------------------------------------------


def stage_all_changes() -> None:
    """Stage all changes for commit."""
    run_command(["git", "add", "-A"], cwd=WORKSPACE_ROOT)


def create_release_commit(version: str) -> None:
    """Create a release commit.

    Args:
        version: The version being released.
    """
    message_lines = [f"chore(release): v{version}", "", f"- workspace: v{version}"]
    commit_message = "\n".join(message_lines)
    run_command(["git", "commit", "-m", commit_message], cwd=WORKSPACE_ROOT)
    print_success(f"Created release commit for v{version}")


def create_release_tag(version: str) -> None:
    """Create a git tag for the release.

    Args:
        version: The version being released.
    """
    run_command(
        ["git", "tag", "-a", f"v{version}", "-m", f"Release v{version}"],
        cwd=WORKSPACE_ROOT,
    )
    print_success(f"Created tag v{version}")


# -----------------------------------------------------------------------------
# GitHub Actions Output
# -----------------------------------------------------------------------------


def write_github_output(key: str, value: str) -> None:
    """Write a key-value pair to GitHub Actions output.

    Args:
        key: Output key name.
        value: Output value.
    """
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as file:
        file.write(f"{key}={value}\n")


# -----------------------------------------------------------------------------
# Main Command
# -----------------------------------------------------------------------------


@app.command()
def main(
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Preview the next version without modifying files.",
        ),
    ] = False,
    tag: Annotated[
        bool,
        typer.Option(
            "--tag",
            "-t",
            help="Create a git tag after the release commit (for local use).",
        ),
    ] = False,
) -> None:
    """Bump versions for the entire workspace."""
    try:
        print_header("Version Bump")

        next_version = get_next_version()
        if next_version is None:
            print_success("No conventional commits requiring a release were found")
            raise typer.Exit(0)

        console.print(f"[bold]Next release version:[/] v{next_version}")

        if dry_run:
            print_info("Dry run - no files modified")
            raise typer.Exit(0)

        perform_commitizen_bump(next_version)
        sync_dependency_versions(next_version)
        refresh_changelogs(next_version)

        stage_all_changes()
        create_release_commit(next_version)

        if tag:
            create_release_tag(next_version)

        packages = get_all_packages()
        write_github_output("released_version", next_version)
        write_github_output("released_packages", json.dumps([p.name for p in packages]))

        print_header("Release Artifacts Generated")

        table = Table(title=f"Released Packages (v{next_version})")
        table.add_column("Package", style="cyan")
        table.add_column("Path", style="green")

        for pkg in packages:
            table.add_row(pkg.name, str(pkg.path))

        console.print(table)

    except BumpError as e:
        print_error(str(e))
        raise typer.Exit(1) from e
    except CommandError as e:
        print_error(str(e))
        raise typer.Exit(1) from e


if __name__ == "__main__":
    app()
