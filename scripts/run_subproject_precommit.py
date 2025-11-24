#!/usr/bin/env python3
"""
Monorepo pre-commit hook that runs sub-project pre-commit configs
only for projects with actual file changes.
"""

import subprocess
import sys
import tomllib  # Python 3.11+ built-in
from pathlib import Path


def get_workspace_members() -> list[str]:
    """Read workspace members from root pyproject.toml."""
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

        if not members:
            print("⚠ No workspace members found in pyproject.toml", file=sys.stderr)
            return []

        return members

    except FileNotFoundError:
        print(f"❌ pyproject.toml not found at {pyproject_path}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"❌ Error reading pyproject.toml: {e}", file=sys.stderr)
        return []


def get_changed_files() -> set[str]:
    """Get list of files that have been staged for commit."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            capture_output=True,
            text=True,
            check=True,
        )
        return (
            set(result.stdout.strip().split("\n")) if result.stdout.strip() else set()
        )
    except subprocess.CalledProcessError as e:
        print(f"Error getting changed files: {e}", file=sys.stderr)
        return set()


def get_changed_projects(
    changed_files: set[str], workspace_members: list[str]
) -> list[str]:
    """Determine which sub-projects have changes."""
    changed_projects: list[str] = []

    for member in workspace_members:
        # Check if any changed file is within this project
        if any(file.startswith(f"{member}/") for file in changed_files):
            project_path = Path(member)
            pre_commit_config = project_path / ".pre-commit-config.yaml"

            if pre_commit_config.exists():
                changed_projects.append(member)
                print(f"✓ Detected changes in: {member}")
            else:
                print(f"⚠ Changes in {member} but no .pre-commit-config.yaml found")

    return changed_projects


def run_pre_commit_for_project(project_path: str) -> bool:
    """Run pre-commit for a specific project."""
    print(f"\n{'=' * 60}")
    print(f"Running pre-commit for: {project_path}")
    print(f"{'=' * 60}\n")
    sys.stdout.flush()  # Ensure header is printed before subprocess output

    try:
        # Run without capturing output - let it stream to terminal in real-time
        result = subprocess.run(
            ["uv", "run", "pre-commit", "run", "--all-files", "--color=always"],
            cwd=project_path,
            check=False,  # Don't raise exception on non-zero exit
            # stdout and stderr will inherit from parent process
        )

        if result.returncode != 0:
            print(f"\n❌ Pre-commit failed for: {project_path}")
            return False

        print(f"\n✅ Pre-commit passed for: {project_path}")
        return True

    except Exception as e:
        print(f"\n❌ Error running pre-commit for {project_path}: {e}", file=sys.stderr)
        return False


def main() -> int:
    """Main entry point."""
    print("🔍 Checking for changed files in workspace members...")

    # Read workspace members from pyproject.toml
    workspace_members = get_workspace_members()
    if not workspace_members:
        print("❌ No workspace members found. Exiting.")
        return 1

    changed_files = get_changed_files()

    if not changed_files:
        print("ℹ️  No staged files detected. Skipping pre-commit checks.")
        return 0

    changed_projects = get_changed_projects(changed_files, workspace_members)

    if not changed_projects:
        print("ℹ️  No changes in workspace members with pre-commit configs.")
        return 0

    print(f"\n📦 Running pre-commit for {len(changed_projects)} project(s)...\n")

    all_passed = True
    for project in changed_projects:
        if not run_pre_commit_for_project(project):
            all_passed = False

    print(f"\n{'=' * 60}")
    if all_passed:
        print("✅ All pre-commit checks passed!")
        print(f"{'=' * 60}\n")
        return 0
    else:
        print("❌ Some pre-commit checks failed!")
        print(f"{'=' * 60}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
