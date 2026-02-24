#!/usr/bin/env python3
"""Monorepo pre-commit hook that runs sub-project pre-commit configs.

This script runs pre-commit checks only for sub-projects that have
actual file changes staged for commit.

Usage:
    uv run python scripts/run_subproject_precommit.py
"""

from __future__ import annotations

import typer

from common import (
    PackageInfo,
    ScriptError,
    console,
    get_all_packages,
    get_changed_packages,
    get_staged_files,
    print_error,
    print_header,
    print_info,
    print_success,
    print_warning,
    run_streaming,
)

app = typer.Typer(
    help="Run pre-commit hooks for changed workspace projects.",
    no_args_is_help=False,
)


def run_precommit_for_package(pkg: PackageInfo) -> bool:
    """Run pre-commit for a specific package.

    Args:
        pkg: Package information.

    Returns:
        True if checks passed, False otherwise.
    """
    print_header(f"Pre-commit: {pkg.name}")

    if not pkg.has_precommit_config:
        print_warning(f"No .pre-commit-config.yaml found for {pkg.name}")
        return True

    cmd = [
        "uv",
        "run",
        "pre-commit",
        "run",
        "--all-files",
        "--color=always",
    ]

    exit_code = run_streaming(cmd, cwd=pkg.full_path)

    if exit_code != 0:
        print_error(f"Pre-commit failed for: {pkg.name}")
        return False

    print_success(f"Pre-commit passed for: {pkg.name}")
    return True


@app.command()
def main(
    all_packages: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Run for all packages instead of only changed ones.",
    ),
) -> None:
    """Run pre-commit checks for workspace projects with staged changes."""
    try:
        print_header("Checking for changes in workspace members")

        packages = get_all_packages()
        if not packages:
            print_error("No workspace packages found.")
            raise typer.Exit(1)

        if all_packages:
            changed_packages = [p for p in packages if p.has_precommit_config]
            print_info(f"Running pre-commit for all {len(changed_packages)} packages")
        else:
            staged_files = get_staged_files()

            if not staged_files:
                print_info("No staged files detected. Skipping pre-commit checks.")
                raise typer.Exit(0)

            changed_packages = [
                p for p in get_changed_packages(staged_files) if p.has_precommit_config
            ]

            if not changed_packages:
                print_info("No changes in workspace members with pre-commit configs.")
                raise typer.Exit(0)

        console.print()
        console.print("[bold]Affected projects:[/]")
        for pkg in changed_packages:
            console.print(f"  • {pkg.name}")

        console.print()
        console.print(
            f"[bold]Running pre-commit for {len(changed_packages)} project(s)...[/]"
        )

        all_passed = True
        for pkg in changed_packages:
            if not run_precommit_for_package(pkg):
                all_passed = False

        console.print()
        console.rule()
        if all_passed:
            print_success("All pre-commit checks passed!")
            raise typer.Exit(0)
        else:
            print_error("Some pre-commit checks failed!")
            raise typer.Exit(1)

    except ScriptError as e:
        print_error(str(e))
        raise typer.Exit(1) from e


if __name__ == "__main__":
    app()
