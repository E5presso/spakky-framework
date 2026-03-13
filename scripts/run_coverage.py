#!/usr/bin/env python3
"""Run tests with coverage for all packages in the workspace.

This script discovers all workspace members and runs pytest with coverage
for each package, generating XML reports for Codecov upload.
Executes checks in parallel for faster feedback while maintaining
stable console output.

Usage:
    uv run python scripts/run_coverage.py
    uv run python scripts/run_coverage.py --package spakky-fastapi
    uv run python scripts/run_coverage.py --sequential
    uv run python scripts/run_coverage.py --skip-integration  # Fast local runs

Output:
    Generates coverage XML files in each package directory:
    - core/spakky/coverage.xml
    - plugins/spakky-fastapi/coverage.xml
    - etc.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text

from common import (
    CapturedResult,
    PackageInfo,
    ScriptError,
    console,
    get_all_packages,
    get_package_by_name,
    print_error,
    print_header,
    print_info,
    print_success,
    run_captured,
    run_streaming,
)

if TYPE_CHECKING:
    from concurrent.futures import Future

app = typer.Typer(
    help="Run tests with coverage for workspace packages.",
    no_args_is_help=False,
)


@dataclass(frozen=True, slots=True)
class CoverageMetrics:
    """Parsed coverage metrics from coverage.xml.

    Attributes:
        line_rate: Line coverage as a percentage (0-100).
        branch_rate: Branch coverage as a percentage (0-100).
        lines_covered: Number of covered lines.
        lines_valid: Total number of measurable lines.
    """

    line_rate: float
    branch_rate: float
    lines_covered: int
    lines_valid: int


@dataclass(frozen=True, slots=True)
class CoverageResult:
    """Result of coverage execution for a package.

    Attributes:
        package: The package that was tested.
        passed: Whether the tests passed.
        output: Captured console output (parallel mode only).
    """

    package: PackageInfo
    passed: bool
    output: str


def _build_coverage_cmd(
    pkg: PackageInfo,
    *,
    is_parallel: bool = False,
    skip_integration: bool = False,
) -> list[str]:
    """Build pytest coverage command for a package.

    Args:
        pkg: Package information.
        is_parallel: If True, disable xdist to avoid nested parallelism.
        skip_integration: If True, skip tests marked with 'integration' marker.
    """
    cmd = [
        "uv",
        "run",
        "pytest",
        f"--cov={pkg.python_name}",
        "--cov-report=xml:coverage.xml",
        "--cov-report=term-missing",
    ]
    if is_parallel:
        # Disable xdist parallelism when running packages in parallel
        cmd.extend(["-n", "0"])
    if skip_integration:
        cmd.extend(["-m", "not integration"])
    return cmd


def run_tests_with_coverage_streaming(
    pkg: PackageInfo,
    *,
    skip_integration: bool = False,
) -> bool:
    """Run pytest with coverage for a specific package (streaming output).

    Args:
        pkg: Package information.
        skip_integration: If True, skip tests marked with 'integration' marker.

    Returns:
        True if tests passed, False otherwise.
    """
    print_header(f"Testing: {pkg.name}")

    exit_code = run_streaming(
        _build_coverage_cmd(pkg, skip_integration=skip_integration),
        cwd=pkg.full_path,
    )

    if exit_code != 0:
        print_error(f"Tests failed for: {pkg.name}")
        return False

    print_success(f"Tests passed for: {pkg.name}")
    return True


def run_tests_with_coverage_captured(
    pkg: PackageInfo,
    *,
    skip_integration: bool = False,
) -> CoverageResult:
    """Run pytest with coverage for a specific package (parallel-safe).

    Args:
        pkg: Package information.
        skip_integration: If True, skip tests marked with 'integration' marker.

    Returns:
        CoverageResult with captured output.
    """
    result: CapturedResult = run_captured(
        _build_coverage_cmd(pkg, is_parallel=True, skip_integration=skip_integration),
        cwd=pkg.full_path,
    )
    return CoverageResult(
        package=pkg,
        passed=result.exit_code == 0,
        output=result.output,
    )


def run_parallel_coverage(
    packages: list[PackageInfo],
    *,
    skip_integration: bool = False,
) -> list[CoverageResult]:
    """Run coverage checks for multiple packages in parallel.

    Args:
        packages: List of packages to test.
        skip_integration: If True, skip tests marked with 'integration' marker.

    Returns:
        List of CoverageResult in the same order as input packages.
    """
    results: dict[str, CoverageResult] = {}
    run_captured_fn = partial(
        run_tests_with_coverage_captured,
        skip_integration=skip_integration,
    )

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
            "[cyan]Running coverage tests...",
            total=len(packages),
        )

        with ThreadPoolExecutor(max_workers=min(len(packages), 8)) as executor:
            future_to_pkg: dict[Future[CoverageResult], PackageInfo] = {
                executor.submit(run_captured_fn, pkg): pkg for pkg in packages
            }

            for future in as_completed(future_to_pkg):
                pkg = future_to_pkg[future]
                result = future.result()
                results[pkg.name] = result

                status = "✓" if result.passed else "✗"
                progress.update(
                    task,
                    advance=1,
                    description=f"[cyan]Completed: {pkg.name} [{status}]",
                )

    return [results[pkg.name] for pkg in packages]


def display_results(results: list[CoverageResult]) -> bool:
    """Display coverage results with stable output.

    Args:
        results: List of CoverageResult from parallel execution.

    Returns:
        True if all tests passed, False otherwise.
    """
    all_passed = True
    failed_results: list[CoverageResult] = []
    passed_results: list[CoverageResult] = []

    for result in results:
        if result.passed:
            passed_results.append(result)
        else:
            failed_results.append(result)
            all_passed = False

    console.print()

    if passed_results:
        console.print("[green]Passed:[/]")
        for result in passed_results:
            console.print(f"  [green]✓[/] {result.package.name}")
        console.print()

    if failed_results:
        console.print("[red]Failed:[/]")
        for result in failed_results:
            console.print(f"  [red]✗[/] {result.package.name}")
        console.print()

        for result in failed_results:
            console.rule(f"[red bold]{result.package.name} - Output[/]")
            ansi_text = Text.from_ansi(result.output)
            console.print(ansi_text)
            console.print()

    return all_passed


def parse_coverage_xml(path: Path) -> CoverageMetrics | None:
    """Parse coverage metrics from a coverage.xml file.

    Args:
        path: Absolute path to coverage.xml.

    Returns:
        CoverageMetrics if the file exists and is parseable, None otherwise.
    """
    if not path.exists():
        return None
    tree = ET.parse(path)  # noqa: S314
    root = tree.getroot()
    return CoverageMetrics(
        line_rate=float(root.get("line-rate", "0")) * 100,
        branch_rate=float(root.get("branch-rate", "0")) * 100,
        lines_covered=int(root.get("lines-covered", "0")),
        lines_valid=int(root.get("lines-valid", "0")),
    )


def _rate_style(rate: float) -> str:
    """Return a Rich style string based on coverage rate."""
    if rate >= 90:
        return "green"
    if rate >= 70:
        return "yellow"
    return "red"


def collect_coverage_files(packages: list[PackageInfo]) -> list[str]:
    """Collect coverage.xml file paths for the given packages.

    Args:
        packages: Packages to collect coverage files for.

    Returns:
        List of relative paths to coverage.xml files.
    """
    coverage_files: list[str] = []

    for pkg in packages:
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
    sequential: bool = typer.Option(
        False,
        "--sequential",
        "-s",
        help="Run checks sequentially (useful for debugging).",
    ),
    skip_integration: bool = typer.Option(
        False,
        "--skip-integration",
        "-S",
        help="Skip tests marked with 'integration' marker (faster local runs).",
    ),
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

        if skip_integration:
            console.print(
                "[yellow bold]Skipping integration tests "
                "(testcontainers not started)[/]"
            )
            console.print()

        if sequential or len(packages) == 1:
            # Sequential mode: streaming output
            all_passed = True
            for pkg in packages:
                if not run_tests_with_coverage_streaming(
                    pkg,
                    skip_integration=skip_integration,
                ):
                    all_passed = False
            tested_count = len(packages)
        else:
            # Parallel mode (default)
            console.print(
                f"[bold]Running coverage in parallel for "
                f"{len(packages)} package(s)...[/]"
            )
            console.print()

            results = run_parallel_coverage(
                packages,
                skip_integration=skip_integration,
            )
            all_passed = display_results(results)
            tested_count = len(results)

        # Print summary
        print_header("Coverage Summary")

        coverage_files = collect_coverage_files(packages)
        if coverage_files:
            table = Table(title="Coverage Metrics")
            table.add_column("Package", style="cyan")
            table.add_column("Lines", justify="right")
            table.add_column("Line %", justify="right")
            table.add_column("Branch %", justify="right")
            table.add_column("File", style="dim")

            for pkg in packages:
                coverage_path = pkg.full_path / "coverage.xml"
                rel_path = f"./{pkg.path}/coverage.xml"
                if rel_path not in coverage_files:
                    continue
                metrics = parse_coverage_xml(coverage_path)
                if metrics is not None:
                    line_style = _rate_style(metrics.line_rate)
                    branch_style = _rate_style(metrics.branch_rate)
                    table.add_row(
                        pkg.name,
                        f"{metrics.lines_covered}/{metrics.lines_valid}",
                        f"[{line_style}]{metrics.line_rate:.1f}%[/]",
                        f"[{branch_style}]{metrics.branch_rate:.1f}%[/]",
                        rel_path,
                    )
                else:
                    table.add_row(pkg.name, "-", "-", "-", rel_path)

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
