#!/usr/bin/env python3
import json
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
        print(f"Error reading pyproject.toml: {e}", file=sys.stderr)
        return []


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
    # Get refs from environment or defaults
    # In GitHub Actions PR: GITHUB_BASE_REF (target branch name)
    # In GitHub Actions Push: usually we compare with previous commit

    # We will rely on the caller to provide the correct refs or handle it here
    # For PRs: origin/main (or target) vs HEAD

    base_ref = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    head_ref = sys.argv[2] if len(sys.argv) > 2 else "HEAD"

    members = get_workspace_members()
    changed_files = get_changed_files(base_ref, head_ref)

    changed_projects = set()

    # Check for changes in each member directory
    for member in members:
        if any(f.startswith(f"{member}/") for f in changed_files):
            changed_projects.add(member)

    # If core framework (spakky) changes, test everything
    if "spakky" in changed_projects:
        changed_projects = set(members)

    # If pyproject.toml or uv.lock changes, test everything
    if "pyproject.toml" in changed_files or "uv.lock" in changed_files:
        changed_projects = set(members)

    # Output JSON list for GitHub Actions matrix
    print(json.dumps(list(changed_projects)))


if __name__ == "__main__":
    main()
