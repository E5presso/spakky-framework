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

Usage::

    python scripts/bump_packages.py [--dry-run] [--tag]

Environment::

    GITHUB_OUTPUT: Optional path for writing GitHub Actions step outputs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Iterable

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


def get_package_paths() -> dict[str, Path]:
    """Read workspace members from root pyproject.toml and build package paths.

    Returns:
        A dictionary mapping package names to their relative paths.
    """
    pyproject_path = WORKSPACE_ROOT / "pyproject.toml"

    with open(pyproject_path, "rb") as f:
        pyproject = tomllib.load(f)

    members = (
        pyproject.get("tool", {}).get("uv", {}).get("workspace", {}).get("members", [])
    )

    package_paths: dict[str, Path] = {}
    for member in members:
        member_pyproject = WORKSPACE_ROOT / member / "pyproject.toml"
        if member_pyproject.exists():
            with open(member_pyproject, "rb") as f:
                member_config = tomllib.load(f)
            package_name = member_config.get("project", {}).get("name", "")
            if package_name:
                package_paths[package_name] = Path(member)

    return package_paths


class BumpError(RuntimeError):
    """Raised when the release process encounters an unrecoverable error."""


def run_command(
    cmd: Iterable[str], *, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Execute a shell command and return the completed process."""
    process = subprocess.run(
        list(cmd),
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise BumpError(
            "Command failed ({}): {}\n{}".format(
                process.returncode,
                " ".join(cmd),
                process.stderr.strip() or process.stdout.strip(),
            )
        )
    return process


def get_next_version() -> str | None:
    """Return the next semantic version as determined by commitizen."""
    process = subprocess.run(
        ["uv", "run", "cz", "bump", "--dry-run", "--yes"],
        cwd=WORKSPACE_ROOT,
        text=True,
        capture_output=True,
    )
    if process.returncode == 21:  # No version bump required
        return None
    if process.returncode != 0:
        raise BumpError(process.stderr.strip() or process.stdout.strip())

    output = process.stdout + process.stderr
    match = re.search(r"bump: version [\d.]+ → ([\d.]+)", output)
    if not match:
        raise BumpError("Unable to parse new version from commitizen output")
    return match.group(1)


def perform_commitizen_bump(new_version: str) -> None:
    """Run commitizen to update version files and the root changelog."""
    process = subprocess.run(
        ["uv", "run", "cz", "bump", "--yes", "--files-only"],
        cwd=WORKSPACE_ROOT,
        text=True,
        capture_output=True,
    )
    if process.returncode != 0:
        raise BumpError(process.stderr.strip() or process.stdout.strip())

    print(f"🔢 Updated workspace version to {new_version} via commitizen")


def replace_pattern(path: Path, pattern: str, replacement: str) -> None:
    """Replace all occurrences of a regex pattern inside a file."""
    content = path.read_text()
    new_content, count = re.subn(pattern, replacement, content)
    if count == 0:
        raise BumpError(f"Pattern '{pattern}' not found in {path}")
    path.write_text(new_content)


def sync_dependency_versions(new_version: str) -> None:
    """Align inter-package version constraints with the new release version."""
    print("🔄 Updating inter-package dependency constraints...")
    package_paths = get_package_paths()
    plugins = [name for name in package_paths if name != "spakky"]

    # Update core's optional dependencies to plugins
    core_pyproject = WORKSPACE_ROOT / "spakky/pyproject.toml"
    for plugin in plugins:
        pattern = rf'"{plugin}>=([\d.]+)"'
        replacement = f'"{plugin}>={new_version}"'
        replace_pattern(core_pyproject, pattern, replacement)

    # Update each plugin's dependency on spakky
    for plugin in plugins:
        plugin_pyproject = WORKSPACE_ROOT / package_paths[plugin] / "pyproject.toml"
        pattern = r'"spakky>=([\d.]+)"'
        replacement = f'"spakky>={new_version}"'
        replace_pattern(plugin_pyproject, pattern, replacement)


def write_changelog(package: str, version: str, package_paths: dict[str, Path]) -> None:
    """Write a minimal changelog entry for the given package."""
    changelog_path = WORKSPACE_ROOT / package_paths[package] / "CHANGELOG.md"
    content = """# Changelog

All notable changes to {pkg} are documented in this file.

See the root CHANGELOG.md for a full summary of modifications affecting the
entire workspace.

## {version}

- Release {version}
""".format(pkg=package, version=version)
    changelog_path.write_text(content)


def refresh_changelogs(version: str) -> None:
    """Regenerate changelog stubs for every package."""
    print("📝 Refreshing package changelog stubs...")
    package_paths = get_package_paths()
    for package in package_paths:
        write_changelog(package, version, package_paths)


def stage_all_changes() -> None:
    run_command(["git", "add", "-A"], cwd=WORKSPACE_ROOT)


def create_release_commit(version: str) -> None:
    message_lines = [f"chore(release): v{version}", "", f"- workspace: v{version}"]
    commit_message = "\n".join(message_lines)
    run_command(["git", "commit", "-m", commit_message], cwd=WORKSPACE_ROOT)
    print(f"📝 Created release commit for v{version}")


def create_release_tag(version: str) -> None:
    run_command(
        ["git", "tag", "-a", f"v{version}", "-m", f"Release v{version}"],
        cwd=WORKSPACE_ROOT,
    )
    print(f"🏷️ Created tag v{version}")


def write_github_output(key: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as file:
        file.write(f"{key}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bump versions for the entire workspace"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the next version without modifying files",
    )
    parser.add_argument(
        "--tag",
        action="store_true",
        help="Create a git tag after the release commit (for local use)",
    )
    args = parser.parse_args()

    next_version = get_next_version()
    if next_version is None:
        print("✅ No conventional commits requiring a release were found")
        return 0

    print(f"📦 Next release version: v{next_version}")

    if args.dry_run:
        return 0

    perform_commitizen_bump(next_version)
    sync_dependency_versions(next_version)
    refresh_changelogs(next_version)

    stage_all_changes()
    create_release_commit(next_version)

    # Create tag only if --tag flag is provided (for local use)
    # In CI, the release workflow creates the tag after uv.lock update
    if args.tag:
        create_release_tag(next_version)

    packages = list(get_package_paths().keys())
    write_github_output("released_version", next_version)
    write_github_output("released_packages", json.dumps(packages))

    print(
        """
========================================
✅ Release artifacts generated
========================================
    """
    )
    for package in packages:
        print(f"  - {package} v{next_version}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BumpError as exc:  # pragma: no cover - invoked via CLI
        print(f"❌ {exc}", file=sys.stderr)
        sys.exit(1)
