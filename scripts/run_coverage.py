#!/usr/bin/env python3
"""Run tests with coverage for all packages in the workspace.

This script discovers all workspace members and runs pytest with coverage
for each package, generating XML reports for Codecov upload.

Usage:
    uv run python scripts/run_coverage.py
    uv run python scripts/run_coverage.py --package spakky-fastapi

Output:
    Generates coverage XML files in each package directory:
    - core/spakky/coverage.xml
    - plugins/spakky-fastapi/coverage.xml
    - etc.
"""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

from common import (
    PackageInfo,
    ScriptError,
    console,
    get_all_packages,
    get_package_by_name,
    print_error,
    print_header,
    print_info,
    print_success,
    run_streaming,
)

app = typer.Typer(
    help="Run tests with coverage for workspace packages.",
    no_args_is_help=False,
)


def run_tests_with_coverage(pkg: PackageInfo) -> bool:
    """Run pytest with coverage for a specific package.

    Args:
        pkg: Package information.

    Returns:
        True if tests passed, False otherwise.
    """
    print_header(f"Testing: {pkg.name}")

    cmd = [
        "uv",
        "run",
        "pytest",
        f"--cov={pkg.python_name}",
        "--cov-report=xml:coverage.xml",
        "--cov-report=term-missing",
    ]

    # Add -n 1 for kafka (port conflict prevention)
    if "kafka" in pkg.name:
        cmd.extend(["-n", "1"])

    exit_code = run_streaming(cmd, cwd=pkg.full_path)

    if exit_code != 0:
        print_error(f"Tests failed for: {pkg.name}")
        return False

    print_success(f"Tests passed for: {pkg.name}")
    return True


def collect_coverage_files() -> list[str]:
    """Collect all coverage.xml file paths.

    Returns:
        List of relative paths to coverage.xml files.
    """
    coverage_files: list[str] = []

    for pkg in get_all_packages():
        coverage_path = pkg.full_path / "coverage.xml"
        if coverage_path.exists():
            coverage_files.append(f"./{pkg.path}/coverage.xml")

    return coverage_files


@app.command()
def main(
    package: Annotated[
        str | None,
        typer.Option(
            "--package",
            "-p",
            help="Run coverage for a specific package only.",
        ),
    ] = None,
) -> None:
    """Run tests with coverage for all (or specific) workspace packages."""
    try:
        print_header("Running tests with coverage")

        if package:
            try:
                pkg = get_package_by_name(package)
                packages = [pkg]
                print_info(f"Running coverage for: {package}")
            except ScriptError as e:
                print_error(str(e))
                raise typer.Exit(1) from e
        else:
            packages = get_all_packages()
            if not packages:
                print_error("No workspace packages found.")
                raise typer.Exit(1)

            print_info(f"Found {len(packages)} packages")

        console.print()
        console.print("[bold]Packages to test:[/]")
        for pkg in packages:
            console.print(f"  • {pkg.name}")
        console.print()

        all_passed = True
        tested_count = 0

        for pkg in packages:
            if not run_tests_with_coverage(pkg):
                all_passed = False
            tested_count += 1

        # Print summary
        print_header("Coverage Summary")

        coverage_files = collect_coverage_files()
        if coverage_files:
            table = Table(title="Generated Coverage Files")
            table.add_column("Package", style="cyan")
            table.add_column("Coverage File", style="green")

            for f in coverage_files:
                # Extract package name from path
                parts = f.split("/")
                if len(parts) >= 3:
                    pkg_name = parts[-2]
                else:
                    pkg_name = f
                table.add_row(pkg_name, f)

            console.print(table)

            # Output for CI consumption
            console.print()
            print_info("Coverage files for upload:")
            console.print(f"[dim]{','.join(coverage_files)}[/]")

        console.print()
        console.rule()
        if all_passed:
            print_success(f"All {tested_count} packages passed!")
            raise typer.Exit(0)
        else:
            print_error("Some packages failed!")
            raise typer.Exit(1)

    except ScriptError as e:
        print_error(str(e))
        raise typer.Exit(1) from e


if __name__ == "__main__":
    app()
