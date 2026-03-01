"""Console output helpers for Spakky workspace scripts."""

from __future__ import annotations

import fcntl
import os
import struct
import sys
import termios
from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from typing import TextIO


def _get_terminal_width_from_tty() -> int | None:
    """Get terminal width by querying /dev/tty directly.

    This works even when stdout/stderr are captured by pre-commit.
    """
    try:
        with open("/dev/tty", "rb") as tty:
            result = fcntl.ioctl(tty.fileno(), termios.TIOCGWINSZ, b"\x00" * 8)
            _, width, _, _ = struct.unpack("HHHH", result)
            return width if width > 0 else None
    except (OSError, struct.error):
        return None


def _get_terminal_width() -> int:
    """Get terminal width for console output.

    Queries /dev/tty directly when available, falls back to os.get_terminal_size,
    and finally defaults to 80. Caps at 120 to prevent excessively wide output.
    """
    # Try to get width from /dev/tty first (works even when stdout is captured)
    width = _get_terminal_width_from_tty()

    if width is None:
        try:
            width = os.get_terminal_size().columns
        except OSError:
            width = 80

    # Cap width to prevent issues with very wide terminals
    return min(width, 120)


def _get_tty_file() -> TextIO | None:
    """Get TTY file for direct terminal output, bypassing pre-commit capturing."""
    try:
        if sys.platform == "win32":
            return open("CON", "w")  # noqa: SIM115
        return open("/dev/tty", "w")  # noqa: SIM115
    except OSError:
        return None


_tty_file = _get_tty_file()
_terminal_width = _get_terminal_width()

# When using TTY file directly, we must specify width explicitly
# because Rich cannot detect terminal size from a raw file handle
console = (
    Console(file=_tty_file, force_terminal=True, width=_terminal_width)
    if _tty_file
    else Console()
)
"""Rich console instance for formatted output."""

err_console = (
    Console(file=_tty_file, force_terminal=True, width=_terminal_width)
    if _tty_file
    else Console(stderr=True)
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
