"""Console output helpers for Spakky workspace scripts."""

from __future__ import annotations

import sys

from rich.console import Console

console = Console()
"""Rich console instance for formatted output."""

err_console = Console(stderr=True)
"""Rich console instance for error output."""


def print_header(text: str) -> None:
    """Print a formatted header."""
    console.print()
    console.rule(f"[bold blue]{text}[/]")
    console.print()


def print_success(text: str) -> None:
    """Print a success message."""
    console.print(f"[green]✓[/] {text}")


def print_error(text: str) -> None:
    """Print an error message."""
    err_console.print(f"[red]✗[/] {text}")


def print_warning(text: str) -> None:
    """Print a warning message."""
    console.print(f"[yellow]![/] {text}")


def print_info(text: str) -> None:
    """Print an info message."""
    console.print(f"[blue]ℹ[/] {text}")


def exit_with_error(message: str, code: int = 1) -> None:
    """Print error message and exit with given code."""
    print_error(message)
    sys.exit(code)
