#!/usr/bin/env python3
"""
Monorepo pre-push hook that runs tests only for projects with changes.
This is separate from pre-commit to avoid slow tests blocking every commit.
"""

import os
import subprocess
import sys
import tomllib
from pathlib import Path


def get_workspace_members() -> list[str]:
    """Read workspace members from root pyproject.toml."""
    root_dir = Path(__file__).parent.parent
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


def get_commits_to_push() -> list[str]:
    """Get list of commits that will be pushed."""
    try:
        # Get the remote and branch being pushed to
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "@{upstream}"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            # No upstream set, compare with origin/HEAD or origin/main
            upstream = "origin/HEAD"
        else:
            upstream = result.stdout.strip()

        # Get commits between upstream and HEAD
        result = subprocess.run(
            ["git", "rev-list", f"{upstream}..HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0 or not result.stdout.strip():
            return []

        return result.stdout.strip().split("\n")

    except Exception:
        return []


def get_changed_files_for_push() -> set[str]:
    """Get files changed in commits that will be pushed."""
    try:
        # Try to get upstream branch
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "@{upstream}"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            upstream = "origin/HEAD"
        else:
            upstream = result.stdout.strip()

        # Get changed files between upstream and HEAD
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{upstream}..HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            # Fallback: get all staged + unstaged changes
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
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
        if any(file.startswith(f"{member}/") for file in changed_files):
            changed_projects.append(member)
            print(f"  ✓ {member}", flush=True)

    return changed_projects


def run_tests_for_project(project_path: str) -> bool:
    """Run pytest for a specific project."""
    print(f"\n{'=' * 60}", flush=True)
    print(f"🧪 Running tests for: {project_path}", flush=True)
    print(f"{'=' * 60}\n", flush=True)

    try:
        # Set up environment for unbuffered output
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["FORCE_COLOR"] = "1"

        # Use Popen to stream output in real-time
        process = subprocess.Popen(
            ["uv", "run", "pytest", "--color=yes"],
            cwd=project_path,
            stdout=None,  # Inherit from parent (direct to terminal)
            stderr=None,  # Inherit from parent (direct to terminal)
            bufsize=0,
            env=env,
        )
        process.wait()

        if process.returncode != 0:
            print(f"\n❌ Tests failed for: {project_path}", flush=True)
            return False

        print(f"\n✅ Tests passed for: {project_path}", flush=True)
        return True

    except Exception as e:
        print(
            f"\n❌ Error running tests for {project_path}: {e}",
            file=sys.stderr,
            flush=True,
        )
        return False


def main() -> int:
    """Main entry point."""
    print("\n🚀 Pre-push: Running tests for changed projects...\n", flush=True)

    workspace_members = get_workspace_members()
    if not workspace_members:
        print("❌ No workspace members found. Exiting.", flush=True)
        return 1

    changed_files = get_changed_files_for_push()

    if not changed_files:
        print("ℹ️  No files to push. Skipping tests.", flush=True)
        return 0

    print(f"📝 {len(changed_files)} files changed in commits to push", flush=True)
    print("\n📦 Affected projects:", flush=True)

    changed_projects = get_changed_projects(changed_files, workspace_members)

    if not changed_projects:
        print("  (none)", flush=True)
        print("\nℹ️  No workspace projects affected. Skipping tests.", flush=True)
        return 0

    print(f"\n🧪 Running tests for {len(changed_projects)} project(s)...", flush=True)

    all_passed = True
    for project in changed_projects:
        if not run_tests_for_project(project):
            all_passed = False

    print(f"\n{'=' * 60}", flush=True)
    if all_passed:
        print("✅ All tests passed! Push proceeding...", flush=True)
        print(f"{'=' * 60}\n", flush=True)
        return 0
    else:
        print("❌ Some tests failed! Push aborted.", flush=True)
        print(f"{'=' * 60}\n", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
