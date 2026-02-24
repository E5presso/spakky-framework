#!/usr/bin/env python3
"""Resolve package name to its directory path in the uv workspace.

This script reads the workspace configuration from the root pyproject.toml
and finds the directory path for a given package name.

Usage:
    uv run python scripts/get_package_path.py spakky-fastapi
    uv run python scripts/get_package_path.py --list

Example:
    uv run python scripts/get_package_path.py spakky-fastapi
    # Output: plugins/spakky-fastapi
"""

from __future__ import annotations

from typing import Annotated

import typer
from common import (
    PackageNotFoundError,
    ScriptError,
    console,
    get_all_packages,
    get_package_by_name,
    print_error,
)
from rich.table import Table

app = typer.Typer(
    help="Resolve package names to directory paths.",
    no_args_is_help=True,
)


@app.command()
def main(
    package_name: Annotated[
        str | None,
        typer.Argument(help="Package name to look up."),
    ] = None,
    list_all: Annotated[
        bool,
        typer.Option(
            "--list",
            "-l",
            help="List all packages in the workspace.",
        ),
    ] = False,
) -> None:
    """Resolve package name to directory path or list all packages."""
    try:
        if list_all:
            # List all packages
            packages = get_all_packages()
            if not packages:
                print_error("No workspace packages found.")
                raise typer.Exit(1)

            table = Table(title="Workspace Packages")
            table.add_column("Package Name", style="cyan")
            table.add_column("Path", style="green")
            table.add_column("Python Name", style="yellow")

            for pkg in packages:
                table.add_row(pkg.name, str(pkg.path), pkg.python_name)

            console.print(table)
            return

        if not package_name:
            console.print("[red]Error:[/] Please provide a package name or use --list")
            console.print()
            console.print("[dim]Usage:[/]")
            console.print("  uv run python scripts/get_package_path.py <package-name>")
            console.print("  uv run python scripts/get_package_path.py --list")
            raise typer.Exit(1)

        # Get path for specific package
        pkg = get_package_by_name(package_name)
        console.print(str(pkg.path))

    except PackageNotFoundError as e:
        print_error(str(e))
        console.print()
        console.print("[dim]Available packages:[/]")
        for p in get_all_packages():
            console.print(f"  {p.name} → {p.path}")
        raise typer.Exit(1) from e
    except ScriptError as e:
        print_error(str(e))
        raise typer.Exit(1) from e


if __name__ == "__main__":
    app()
