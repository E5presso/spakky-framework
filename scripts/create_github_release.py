#!/usr/bin/env python3
"""Create a GitHub release with changelog notes.

This script creates a GitHub release using the gh CLI tool,
extracting release notes from the package's CHANGELOG.md.

Usage:
    python scripts/create_github_release.py <package> <version> <tag> <pkg_path>

Example:
    python scripts/create_github_release.py spakky 3.1.2 spakky-v3.1.2 spakky

Environment:
    GH_TOKEN: GitHub token for authentication (required)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def get_release_notes(pkg_path: Path, tag: str, max_lines: int = 100) -> str:
    """Get release notes from CHANGELOG.md or generate default.

    Args:
        pkg_path: Path to the package directory.
        tag: The release tag.
        max_lines: Maximum number of lines to include from changelog.

    Returns:
        Release notes string.
    """
    changelog_path = pkg_path / "CHANGELOG.md"

    if changelog_path.exists():
        with open(changelog_path) as f:
            lines = f.readlines()[:max_lines]
        return "".join(lines)

    return f"Release {tag}"


def create_release(
    package: str,
    version: str,
    tag: str,
    pkg_path: Path,
) -> bool:
    """Create a GitHub release.

    Args:
        package: The package name.
        version: The version string.
        tag: The git tag.
        pkg_path: Path to the package directory.

    Returns:
        True if successful, False otherwise.
    """
    notes = get_release_notes(pkg_path, tag)
    title = f"{package} {version}"

    result = subprocess.run(
        [
            "gh",
            "release",
            "create",
            tag,
            "--title",
            title,
            "--notes",
            notes,
            "dist/*",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        print(f"✅ Created GitHub release: {title}")
        return True
    else:
        # Release may already exist
        if "already exists" in result.stderr.lower():
            print(f"ℹ️ Release {tag} already exists")
            return True
        print(f"❌ Failed to create release: {result.stderr}")
        return False


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 5:
        print(
            "Usage: python create_github_release.py <package> <version> <tag> <pkg_path>",
            file=sys.stderr,
        )
        return 1

    package = sys.argv[1]
    version = sys.argv[2]
    tag = sys.argv[3]
    pkg_path = Path(sys.argv[4])

    success = create_release(package, version, tag, pkg_path)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
