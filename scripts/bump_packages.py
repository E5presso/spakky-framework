#!/usr/bin/env python3
"""Bump versions for all packages in the workspace.

This script handles version bumping for all packages, auto-detecting
first releases (no existing tags) and using commitizen for version management.

Usage:
    python scripts/bump_packages.py [--dry-run]

Environment:
    GITHUB_OUTPUT: Path to GitHub Actions output file (optional)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from get_package_path import get_all_packages


@dataclass
class ReleaseInfo:
    """Information about a released package."""

    package: str
    version: str
    tag: str


def run_command(
    cmd: list[str],
    cwd: Path | None = None,
    check: bool = True,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a shell command."""
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=check,
        capture_output=capture_output,
        text=True,
    )


def get_existing_tags(package: str) -> list[str]:
    """Get existing version tags for a package."""
    result = run_command(["git", "tag", "-l", f"{package}-v*"], check=False)
    if result.returncode != 0:
        return []
    return [tag for tag in result.stdout.strip().split("\n") if tag]


def get_current_version(pkg_path: Path) -> str:
    """Get current version from pyproject.toml using commitizen."""
    result = run_command(["uv", "run", "cz", "version", "--project"], cwd=pkg_path)
    return result.stdout.strip()


def create_tag(tag: str, message: str) -> None:
    """Create an annotated git tag."""
    run_command(["git", "tag", "-a", tag, "-m", message])


def bump_version(pkg_path: Path) -> tuple[bool, int]:
    """Bump version using commitizen.

    Returns:
        Tuple of (success, exit_code)
    """
    result = run_command(
        ["uv", "run", "cz", "bump", "--yes", "--changelog"],
        cwd=pkg_path,
        check=False,
    )
    return result.returncode == 0, result.returncode


def bump_version_dry_run(pkg_path: Path) -> None:
    """Show what version bump would happen."""
    run_command(
        ["uv", "run", "cz", "bump", "--dry-run", "--yes"],
        cwd=pkg_path,
        check=False,
    )


def write_github_output(key: str, value: str) -> None:
    """Write output to GitHub Actions."""
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"{key}={value}\n")


def process_package(
    package: str,
    pkg_path: Path,
    dry_run: bool,
) -> ReleaseInfo | None:
    """Process a single package for release.

    Returns:
        ReleaseInfo if package was released, None otherwise.
    """
    print()
    print("=" * 40)
    print(f"📦 Processing: {package}")
    print("=" * 40)
    print(f"📁 Path: {pkg_path}")

    # Auto-detect first release
    existing_tags = get_existing_tags(package)
    is_first_release = len(existing_tags) == 0

    if is_first_release:
        print("🆕 First release detected (no existing tags)")
    else:
        print("📋 Existing releases found")

    if dry_run:
        print("🔍 Dry run mode:")
        if is_first_release:
            version = get_current_version(pkg_path)
            print(f"  Would create first release: {package}-v{version}")
        else:
            bump_version_dry_run(pkg_path)
        return None

    # Actual release
    if is_first_release:
        version = get_current_version(pkg_path)
        tag = f"{package}-v{version}"
        print(f"📌 First release version: {version}")

        create_tag(tag, f"Release {tag}")
        print(f"🏷️ Created tag: {tag}")

        return ReleaseInfo(package=package, version=version, tag=tag)
    else:
        success, exit_code = bump_version(pkg_path)

        if success:
            version = get_current_version(pkg_path)
            tag = f"{package}-v{version}"
            print(f"✅ Bumped to: {version}")
            return ReleaseInfo(package=package, version=version, tag=tag)
        elif exit_code == 21:
            print(f"⚠️ No commits to bump for {package} - skipping")
            return None
        else:
            print(f"❌ Failed to bump {package}")
            sys.exit(exit_code)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Bump versions for all packages")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without making changes",
    )
    args = parser.parse_args()

    workspace_root = Path.cwd()
    packages = get_all_packages(workspace_root)

    if not packages:
        print("❌ No packages found in workspace")
        return 1

    released: list[ReleaseInfo] = []

    for package, relative_path in packages.items():
        pkg_path = workspace_root / relative_path
        result = process_package(package, pkg_path, args.dry_run)
        if result:
            released.append(result)

    # Output results
    if released:
        print()
        print("=" * 40)
        print(f"📋 Released packages: {', '.join(r.package for r in released)}")
        print("=" * 40)

        # Format for GitHub Actions
        released_info = ";".join(f"{r.package}:{r.version}:{r.tag}" for r in released)
        released_packages = json.dumps([r.package for r in released])

        write_github_output("released", released_info)
        write_github_output("released_packages", released_packages)

        # Also print for local debugging
        print(f"\nreleased={released_info}")
        print(f"released_packages={released_packages}")
    else:
        print()
        print("ℹ️ No packages were released")
        write_github_output("released", "")
        write_github_output("released_packages", "[]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
