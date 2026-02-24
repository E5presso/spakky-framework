#!/usr/bin/env python3
"""Monorepo pre-push hook that runs pre-push stage hooks for changed projects.

This script delegates to each sub-project's own .pre-commit-config.yaml,
running hooks registered in the 'pre-push' stage (including pytest).
This ensures sub-projects work independently when opened standalone.

Usage:
    uv run python scripts/run_subproject_prepush.py
"""

from __future__ import annotations

import typer
from common import (
    PackageInfo,
    ScriptError,
    console,
    get_all_packages,
    get_changed_packages,
    get_files_to_push,
    print_error,
    print_header,
    print_info,
    print_success,
    print_warning,
    run_streaming,
)

app = typer.Typer(
    help="Run pre-push hooks for changed workspace projects.",
    no_args_is_help=False,
)


def run_prepush_for_package(pkg: PackageInfo) -> bool:
    """Run pre-push hooks for a specific package.

    Args:
        pkg: Package information.

    Returns:
        True if hooks passed, False otherwise.
    """
    print_header(f"Pre-push hooks: {pkg.name}")

    if not pkg.has_precommit_config:
        print_warning(f"No .pre-commit-config.yaml found for {pkg.name}")
        return True

    cmd = [
        "uv",
        "run",
        "pre-commit",
        "run",
        "--hook-stage",
        "pre-push",
        "--all-files",
        "-c",
        str(pkg.full_path / ".pre-commit-config.yaml"),
        "--color=always",
    ]

    exit_code = run_streaming(cmd)

    if exit_code != 0:
        print_error(f"Pre-push hooks failed for: {pkg.name}")
        return False

    print_success(f"Pre-push hooks passed for: {pkg.name}")
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
    """Run pre-push hooks for workspace projects with changes."""
    try:
        print_header("Pre-push: Running tests for changed projects")

        packages = get_all_packages()
        if not packages:
            print_error("No workspace packages found.")
            raise typer.Exit(1)

        if all_packages:
            changed_packages = packages
            print_info(f"Running pre-push hooks for all {len(packages)} packages")
        else:
            changed_files = get_files_to_push()

            if not changed_files:
                print_info("No files to push. Skipping tests.")
                raise typer.Exit(0)

            console.print(
                f"[dim]{len(changed_files)} files changed in commits to push[/]"
            )

            changed_packages = get_changed_packages(changed_files)

            if not changed_packages:
                print_info("No workspace projects affected. Skipping tests.")
                raise typer.Exit(0)

        console.print()
        console.print("[bold]Affected projects:[/]")
        for pkg in changed_packages:
            console.print(f"  • {pkg.name} ([dim]{pkg.path}[/])")

        console.print()
        console.print(
            f"[bold]Running pre-push hooks for {len(changed_packages)} project(s)...[/]"
        )

        all_passed = True
        for pkg in changed_packages:
            if not run_prepush_for_package(pkg):
                all_passed = False

        console.print()
        console.rule()
        if all_passed:
            print_success("All pre-push hooks passed! Push proceeding...")
            raise typer.Exit(0)
        else:
            print_error("Some pre-push hooks failed! Push aborted.")
            raise typer.Exit(1)

    except ScriptError as e:
        print_error(str(e))
        raise typer.Exit(1) from e


if __name__ == "__main__":
    app()
