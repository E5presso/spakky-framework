#!/usr/bin/env python3
"""Detect changed packages in the monorepo for CI matrix generation.

This script analyzes git changes and outputs a JSON list of package names
that need to be tested. It handles workspace member detection and
cascading changes (e.g., core changes trigger all package tests).

Usage:
    uv run python scripts/detect_ci_changes.py
    uv run python scripts/detect_ci_changes.py --base origin/main --head HEAD

Output:
    JSON array of package names: ["spakky", "spakky-fastapi"]
"""

from __future__ import annotations

import json
from typing import Annotated

import typer

from common import (
    ScriptError,
    console,
    err_console,
    get_all_packages,
    get_changed_files_between,
    get_changed_packages,
    print_error,
)

app = typer.Typer(
    help="Detect changed packages for CI matrix generation.",
    no_args_is_help=False,
)


CORE_PACKAGE_NAME = "spakky"
"""Name of the core package that triggers full test runs when changed."""

ROOT_FILES_TRIGGER_ALL = frozenset({"pyproject.toml", "uv.lock"})
"""Root files that trigger full test runs when changed."""


@app.command()
def main(
    base_ref: Annotated[
        str,
        typer.Option("--base", "-b", help="Base git reference for comparison."),
    ] = "origin/main",
    head_ref: Annotated[
        str,
        typer.Option("--head", "-h", help="Head git reference for comparison."),
    ] = "HEAD",
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show detailed output to stderr."),
    ] = False,
) -> None:
    """Detect changed packages and output JSON list for CI matrix."""
    try:
        packages = get_all_packages()
        if not packages:
            print_error("No workspace packages found.")
            raise typer.Exit(1)

        all_package_names = {pkg.name for pkg in packages}
        changed_files = get_changed_files_between(base_ref, head_ref)

        if verbose:
            err_console.print(f"[dim]Comparing {base_ref}...{head_ref}[/]")
            err_console.print(f"[dim]Found {len(changed_files)} changed files[/]")

        changed_packages = get_changed_packages(changed_files)
        changed_package_names = {pkg.name for pkg in changed_packages}

        # If core framework changes, test everything
        if CORE_PACKAGE_NAME in changed_package_names:
            if verbose:
                err_console.print(
                    f"[yellow]Core package '{CORE_PACKAGE_NAME}' changed, "
                    "testing all packages[/]"
                )
            changed_package_names = all_package_names

        # If root config files change, test everything
        if changed_files & ROOT_FILES_TRIGGER_ALL:
            if verbose:
                err_console.print(
                    "[yellow]Root config files changed, testing all packages[/]"
                )
            changed_package_names = all_package_names

        # Output JSON for GitHub Actions matrix
        result = sorted(changed_package_names)
        console.print(json.dumps(result))

        if verbose:
            err_console.print(f"[dim]Output: {len(result)} packages[/]")

    except ScriptError as e:
        print_error(str(e))
        raise typer.Exit(1) from e


if __name__ == "__main__":
    app()
