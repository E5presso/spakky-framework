"""Console output helpers for Spakky workspace scripts."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from typing import TextIO


def _get_tty_file() -> TextIO | None:
    """Get TTY file for direct terminal output, bypassing pre-commit capturing."""
    try:
        if sys.platform == "win32":
            return open("CON", "w")  # noqa: SIM115
        return open("/dev/tty", "w")  # noqa: SIM115
    except OSError:
        return None


_tty_file = _get_tty_file()

console = Console(file=_tty_file, force_terminal=True) if _tty_file else Console()
"""Rich console instance for formatted output."""

err_console = (
    Console(file=_tty_file, force_terminal=True) if _tty_file else Console(stderr=True)
)
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
