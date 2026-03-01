#!/usr/bin/env python3
"""Monorepo pre-push hook that runs pre-push stage hooks for changed projects.

This script delegates to each sub-project's own .pre-commit-config.yaml,
running hooks registered in the 'pre-push' stage (including pytest).
Executes checks in parallel for faster feedback while maintaining stable
console output.

Usage:
    uv run python scripts/run_subproject_prepush.py
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import TYPE_CHECKING

import typer
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.text import Text

from common import (
    CapturedResult,
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
    run_captured,
)

if TYPE_CHECKING:
    from concurrent.futures import Future

app = typer.Typer(
    help="Run pre-push hooks for changed workspace projects.",
    no_args_is_help=False,
)


@dataclass(frozen=True, slots=True)
class PrepushResult:
    """Result of pre-push execution for a package.

    Attributes:
        package: The package that was checked.
        passed: Whether the hooks passed.
        output: Captured console output.
        skipped: Whether the package was skipped (no config).
    """

    package: PackageInfo
    passed: bool
    output: str
    skipped: bool = False


def run_prepush_for_package(pkg: PackageInfo) -> PrepushResult:
    """Run pre-push hooks for a specific package (parallel-safe).

    Args:
        pkg: Package information.

    Returns:
        PrepushResult with captured output.
    """
    if not pkg.has_precommit_config:
        return PrepushResult(
            package=pkg,
            passed=True,
            output="",
            skipped=True,
        )

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

    result: CapturedResult = run_captured(cmd)

    return PrepushResult(
        package=pkg,
        passed=result.exit_code == 0,
        output=result.output,
    )


def run_parallel_prepush(packages: list[PackageInfo]) -> list[PrepushResult]:
    """Run pre-push hooks for multiple packages in parallel.

    Args:
        packages: List of packages to check.

    Returns:
        List of PrepushResult in the same order as input packages.
    """
    results: dict[str, PrepushResult] = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task(
            "[cyan]Running pre-push hooks...",
            total=len(packages),
        )

        with ThreadPoolExecutor(max_workers=min(len(packages), 8)) as executor:
            future_to_pkg: dict[Future[PrepushResult], PackageInfo] = {
                executor.submit(run_prepush_for_package, pkg): pkg for pkg in packages
            }

            for future in as_completed(future_to_pkg):
                pkg = future_to_pkg[future]
                result = future.result()
                results[pkg.name] = result

                # Update progress with status
                status = "✓" if result.passed else "✗"
                if result.skipped:
                    status = "○"
                progress.update(
                    task,
                    advance=1,
                    description=f"[cyan]Completed: {pkg.name} [{status}]",
                )

    # Return results in original package order
    return [results[pkg.name] for pkg in packages]


def display_results(results: list[PrepushResult]) -> bool:
    """Display pre-push results with stable output.

    Args:
        results: List of PrepushResult from parallel execution.

    Returns:
        True if all hooks passed, False otherwise.
    """
    all_passed = True
    failed_packages: list[PrepushResult] = []
    passed_packages: list[PrepushResult] = []
    skipped_packages: list[PrepushResult] = []

    for result in results:
        if result.skipped:
            skipped_packages.append(result)
        elif result.passed:
            passed_packages.append(result)
        else:
            failed_packages.append(result)
            all_passed = False

    console.print()

    # Show skipped packages briefly
    if skipped_packages:
        console.print("[dim]Skipped (no .pre-commit-config.yaml):[/]")
        for result in skipped_packages:
            console.print(f"  [dim]○ {result.package.name}[/]")
        console.print()

    # Show passed packages briefly
    if passed_packages:
        console.print("[green]Passed:[/]")
        for result in passed_packages:
            console.print(f"  [green]✓[/] {result.package.name}")
        console.print()

    # Show failed packages with full output
    if failed_packages:
        console.print("[red]Failed:[/]")
        for result in failed_packages:
            console.print(f"  [red]✗[/] {result.package.name}")
        console.print()

        # Display detailed output for failed packages
        for result in failed_packages:
            console.rule(f"[red bold]{result.package.name} - Output[/]")
            # Parse ANSI codes properly for stable output
            ansi_text = Text.from_ansi(result.output)
            console.print(ansi_text)
            console.print()

    return all_passed


@app.command()
def main(
    all_packages: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Run for all packages instead of only changed ones.",
    ),
    sequential: bool = typer.Option(
        False,
        "--sequential",
        "-s",
        help="Run hooks sequentially (useful for debugging).",
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

        if sequential:
            # Legacy sequential mode for debugging
            from common import run_streaming

            console.print(
                f"[bold]Running pre-push hooks sequentially for "
                f"{len(changed_packages)} project(s)...[/]"
            )

            all_passed = True
            for pkg in changed_packages:
                print_header(f"Pre-push hooks: {pkg.name}")
                if not pkg.has_precommit_config:
                    print_warning(f"No .pre-commit-config.yaml found for {pkg.name}")
                    continue

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
                    all_passed = False
                else:
                    print_success(f"Pre-push hooks passed for: {pkg.name}")
        else:
            # Parallel mode (default)
            console.print(
                f"[bold]Running pre-push hooks in parallel for "
                f"{len(changed_packages)} project(s)...[/]"
            )
            console.print()

            results = run_parallel_prepush(changed_packages)
            all_passed = display_results(results)

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
