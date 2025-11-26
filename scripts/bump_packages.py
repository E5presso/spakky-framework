#!/usr/bin/env python3
"""Unified version bump for all packages in the workspace.

This script handles version bumping for all packages with:
- Single commit containing all version changes
- Individual tags per package
- Changelog limited to latest release only
- Automatic dependency version synchronization

Usage:
    python scripts/bump_packages.py [--dry-run]

Environment:
    GITHUB_OUTPUT: Path to GitHub Actions output file (optional)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from get_package_path import get_all_packages


@dataclass
class ReleaseInfo:
    """Information about a released package."""

    package: str
    version: str
    tag: str
    changelog_entry: str = ""


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
    """Get current version from pyproject.toml."""
    pyproject_path = pkg_path / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)
    return data["project"]["version"]


def get_next_version(pkg_path: Path) -> tuple[str | None, str]:
    """Get next version using commitizen dry-run.

    Returns:
        Tuple of (next_version, changelog_entry). next_version is None if no bump needed.
    """
    result = run_command(
        ["uv", "run", "cz", "bump", "--dry-run", "--yes"],
        cwd=pkg_path,
        check=False,
    )

    # Exit code 21 means no commits to bump
    if result.returncode == 21:
        return None, ""

    if result.returncode != 0:
        return None, ""

    # Parse the output to get the next version
    output = result.stdout + result.stderr
    version_match = re.search(r"bump: version [\d.]+ → ([\d.]+)", output)
    if version_match:
        return version_match.group(1), ""

    return None, ""


def update_version_in_pyproject(pkg_path: Path, new_version: str) -> None:
    """Update version in pyproject.toml."""
    pyproject_path = pkg_path / "pyproject.toml"
    with open(pyproject_path) as f:
        content = f.read()

    # Update [project] version
    content = re.sub(
        r'(\[project\].*?version\s*=\s*")[^"]+(")',
        rf"\g<1>{new_version}\g<2>",
        content,
        flags=re.DOTALL,
    )

    # Update [tool.commitizen] version
    content = re.sub(
        r'(\[tool\.commitizen\].*?version\s*=\s*")[^"]+(")',
        rf"\g<1>{new_version}\g<2>",
        content,
        flags=re.DOTALL,
    )

    with open(pyproject_path, "w") as f:
        f.write(content)


def generate_changelog_entry(pkg_path: Path, version: str) -> str:
    """Generate changelog entry for the version."""
    result = run_command(
        ["uv", "run", "cz", "changelog", "--dry-run", "--unreleased-version", version],
        cwd=pkg_path,
        check=False,
    )
    if result.returncode == 0:
        return result.stdout
    return f"## {version}\n\n- Release {version}\n"


def write_changelog(pkg_path: Path, version: str, entry: str) -> None:
    """Write changelog with only the latest release.

    Previous releases are preserved in GitHub Releases.
    """
    changelog_path = pkg_path / "CHANGELOG.md"

    # Get package name for the header
    pyproject_path = pkg_path / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)
    package_name = data["project"]["name"]

    content = f"""# Changelog

All notable changes to {package_name} will be documented in this file.

See [GitHub Releases](https://github.com/E5presso/spakky-framework/releases) for full release history.

{entry}
"""

    with open(changelog_path, "w") as f:
        f.write(content)


def update_dependency_versions(
    workspace_root: Path,
    packages: dict[str, str],
    new_versions: dict[str, str],
) -> None:
    """Update inter-package dependency versions.

    When spakky is released at 3.1.2, update all plugins to require spakky>=3.1.2
    """
    core_version = new_versions.get("spakky")
    if not core_version:
        return

    for package, relative_path in packages.items():
        if package == "spakky":
            continue

        pkg_path = workspace_root / relative_path
        pyproject_path = pkg_path / "pyproject.toml"

        with open(pyproject_path) as f:
            content = f.read()

        # Update spakky dependency version
        content = re.sub(
            r'"spakky>=[\d.]+"',
            f'"spakky>={core_version}"',
            content,
        )

        with open(pyproject_path, "w") as f:
            f.write(content)

        print(f"  📦 Updated {package}: spakky>={core_version}")


def update_optional_dependencies(
    workspace_root: Path,
    packages: dict[str, str],
    new_versions: dict[str, str],
) -> None:
    """Update optional dependencies in core spakky package."""
    core_path = workspace_root / packages.get("spakky", "spakky")
    pyproject_path = core_path / "pyproject.toml"

    with open(pyproject_path) as f:
        content = f.read()

    for package, version in new_versions.items():
        if package == "spakky":
            continue
        # Update optional dependency version
        content = re.sub(
            rf'"{package}>=[\d.]+"',
            f'"{package}>={version}"',
            content,
        )

    with open(pyproject_path, "w") as f:
        f.write(content)


def create_tags(releases: list[ReleaseInfo]) -> None:
    """Create annotated git tags for all releases."""
    for release in releases:
        run_command(
            [
                "git",
                "tag",
                "-a",
                release.tag,
                "-m",
                f"Release {release.tag}",
            ]
        )
        print(f"  🏷️ Created tag: {release.tag}")


def commit_all_changes(releases: list[ReleaseInfo]) -> None:
    """Create a single commit with all version changes."""
    # Stage all changes
    run_command(["git", "add", "-A"])

    # Build commit message
    package_list = ", ".join(f"{r.package} {r.version}" for r in releases)
    commit_msg = f"chore(release): {package_list}\n\n"

    for release in releases:
        commit_msg += f"- {release.package}: v{release.version}\n"

    run_command(["git", "commit", "-m", commit_msg])
    print(f"  📝 Created unified commit for {len(releases)} packages")


def write_github_output(key: str, value: str) -> None:
    """Write output to GitHub Actions."""
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"{key}={value}\n")


def process_packages(
    workspace_root: Path,
    packages: dict[str, str],
    dry_run: bool,
) -> list[ReleaseInfo]:
    """Process all packages for release.

    Returns:
        List of ReleaseInfo for released packages.
    """
    releases: list[ReleaseInfo] = []
    new_versions: dict[str, str] = {}

    print("\n" + "=" * 50)
    print("🔍 Analyzing packages for version bumps...")
    print("=" * 50)

    # First pass: determine what needs to be released
    for package, relative_path in packages.items():
        pkg_path = workspace_root / relative_path
        print(f"\n📦 {package}")

        existing_tags = get_existing_tags(package)
        is_first_release = len(existing_tags) == 0

        if is_first_release:
            version = get_current_version(pkg_path)
            print(f"  🆕 First release: v{version}")
            new_versions[package] = version
            releases.append(
                ReleaseInfo(
                    package=package,
                    version=version,
                    tag=f"{package}-v{version}",
                )
            )
        else:
            next_version, _ = get_next_version(pkg_path)
            if next_version:
                print(f"  ⬆️ Will bump to: v{next_version}")
                new_versions[package] = next_version
                releases.append(
                    ReleaseInfo(
                        package=package,
                        version=next_version,
                        tag=f"{package}-v{next_version}",
                    )
                )
            else:
                print("  ⏭️ No changes to release")

    if not releases:
        print("\n⚠️ No packages to release")
        return []

    if dry_run:
        print("\n" + "=" * 50)
        print("🔍 DRY RUN - No changes made")
        print("=" * 50)
        print("\nWould release:")
        for r in releases:
            print(f"  - {r.package} v{r.version} ({r.tag})")
        return []

    print("\n" + "=" * 50)
    print("📝 Applying changes...")
    print("=" * 50)

    # Second pass: apply version updates
    for release in releases:
        pkg_path = workspace_root / packages[release.package]

        # Update version in pyproject.toml
        update_version_in_pyproject(pkg_path, release.version)
        print(f"  ✅ Updated {release.package} to v{release.version}")

        # Generate and write changelog (latest only)
        entry = generate_changelog_entry(pkg_path, release.version)
        write_changelog(pkg_path, release.version, entry)
        release.changelog_entry = entry

    # Update inter-package dependencies
    print("\n📦 Updating dependency versions...")
    update_dependency_versions(workspace_root, packages, new_versions)
    update_optional_dependencies(workspace_root, packages, new_versions)

    # Create single commit
    print("\n📝 Creating unified commit...")
    commit_all_changes(releases)

    # Create tags
    print("\n🏷️ Creating tags...")
    create_tags(releases)

    return releases


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

    released = process_packages(workspace_root, packages, args.dry_run)

    # Output results
    if released:
        print("\n" + "=" * 50)
        print(f"✅ Released {len(released)} packages")
        print("=" * 50)
        for r in released:
            print(f"  - {r.package} v{r.version}")

        # Format for GitHub Actions
        released_info = ";".join(f"{r.package}:{r.version}:{r.tag}" for r in released)
        released_packages = json.dumps([r.package for r in released])

        write_github_output("released", released_info)
        write_github_output("released_packages", released_packages)

        return 0

    print("\n✅ No packages needed release")
    return 0


if __name__ == "__main__":
    sys.exit(main())
