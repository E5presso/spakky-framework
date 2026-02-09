#!/usr/bin/env python3
"""Run tests with coverage for all packages in the workspace.

This script discovers all workspace members and runs pytest with coverage
for each package, generating XML reports for Codecov upload.

Usage:
    python scripts/run_coverage.py

Output:
    Generates coverage XML files in each package directory:
    - spakky/coverage.xml
    - plugins/spakky-fastapi/coverage.xml
    - etc.
"""

import subprocess
import sys
import tomllib
from pathlib import Path


def get_workspace_root() -> Path:
    """Get the workspace root directory."""
    return Path(__file__).parent.parent


def get_workspace_members() -> list[str]:
    """Read workspace members from root pyproject.toml."""
    root_dir = get_workspace_root()
    pyproject_path = root_dir / "pyproject.toml"

    try:
        with open(pyproject_path, "rb") as f:
            pyproject = tomllib.load(f)

        return (
            pyproject.get("tool", {})
            .get("uv", {})
            .get("workspace", {})
            .get("members", [])
        )
    except Exception as e:
        print(f"❌ Error reading pyproject.toml: {e}", file=sys.stderr)
        return []


def get_package_name(member_path: str) -> str | None:
    """Get the package name from a member's pyproject.toml."""
    root_dir = get_workspace_root()
    pyproject_path = root_dir / member_path / "pyproject.toml"

    try:
        with open(pyproject_path, "rb") as f:
            pyproject = tomllib.load(f)

        return pyproject.get("project", {}).get("name", "").replace("-", "_")
    except Exception:
        return None


def run_tests_with_coverage(member_path: str, package_name: str) -> bool:
    """Run pytest with coverage for a specific package.

    Args:
        member_path: Path to the package directory (e.g., "plugins/spakky-kafka").
        package_name: Python package name for coverage (e.g., "spakky.plugins.kafka").

    Returns:
        True if tests passed, False otherwise.
    """
    root_dir = get_workspace_root()
    full_path = root_dir / member_path

    print(f"\n{'=' * 60}", flush=True)
    print(f"🧪 Running tests for: {member_path} ({package_name})", flush=True)
    print(f"{'=' * 60}\n", flush=True)

    # Build pytest command
    cmd = [
        "uv",
        "run",
        "pytest",
        f"--cov={package_name}",
        "--cov-report=xml:coverage.xml",
        "--cov-report=term-missing",
    ]

    # Add -n 1 for kafka (port conflict prevention)
    if "kafka" in member_path:
        cmd.append("-n")
        cmd.append("1")

    try:
        process = subprocess.Popen(
            cmd,
            cwd=full_path,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        process.wait()

        if process.returncode != 0:
            print(f"\n❌ Tests failed for: {member_path}", flush=True)
            return False

        print(f"\n✅ Tests passed for: {member_path}", flush=True)
        return True

    except Exception as e:
        print(
            f"\n❌ Error running tests for {member_path}: {e}",
            file=sys.stderr,
            flush=True,
        )
        return False


def collect_coverage_files() -> list[str]:
    """Collect all coverage.xml file paths."""
    root_dir = get_workspace_root()
    members = get_workspace_members()
    coverage_files: list[str] = []

    for member in members:
        coverage_path = root_dir / member / "coverage.xml"
        if coverage_path.exists():
            # Return relative path from root
            coverage_files.append(f"./{member}/coverage.xml")

    return coverage_files


def main() -> int:
    """Main entry point."""
    print("\n🚀 Running tests with coverage for all packages...\n", flush=True)

    workspace_members = get_workspace_members()
    if not workspace_members:
        print("❌ No workspace members found. Exiting.", flush=True)
        return 1

    print(f"📦 Found {len(workspace_members)} packages:", flush=True)
    for member in workspace_members:
        print(f"  • {member}", flush=True)

    all_passed = True
    tested_packages = 0

    for member in workspace_members:
        package_name = get_package_name(member)
        if not package_name:
            print(f"\n⚠️  Skipping {member}: Could not determine package name")
            continue

        if not run_tests_with_coverage(member, package_name):
            all_passed = False
        tested_packages += 1

    # Print summary
    print(f"\n{'=' * 60}", flush=True)
    print("📊 Coverage Summary", flush=True)
    print(f"{'=' * 60}", flush=True)

    coverage_files = collect_coverage_files()
    if coverage_files:
        print("\nGenerated coverage files:", flush=True)
        for f in coverage_files:
            print(f"  • {f}", flush=True)

        # Output for CI consumption
        print("\n📤 Coverage files for upload:", flush=True)
        print(",".join(coverage_files), flush=True)

    print(f"\n{'=' * 60}", flush=True)
    if all_passed:
        print(f"✅ All {tested_packages} packages passed!", flush=True)
        print(f"{'=' * 60}\n", flush=True)
        return 0
    else:
        print("❌ Some packages failed!", flush=True)
        print(f"{'=' * 60}\n", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
