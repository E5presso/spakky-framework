"""Error classes for Spakky workspace scripts."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


class ScriptError(Exception):
    """Base error for all script operations."""

    message: str = "An error occurred during script execution."

    def __init__(self) -> None:
        super().__init__(self.message)


class PyprojectNotFoundError(ScriptError):
    """Raised when pyproject.toml cannot be found."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.message = f"pyproject.toml not found at {path}"
        super().__init__()


class WorkspaceMembersNotFoundError(ScriptError):
    """Raised when no workspace members are found."""

    message = "No workspace members found in pyproject.toml."


class PackageNotFoundError(ScriptError):
    """Raised when a package cannot be found."""

    def __init__(self, package_name: str) -> None:
        self.package_name = package_name
        self.message = f"Package '{package_name}' not found in workspace."
        super().__init__()


class CommandError(ScriptError):
    """Raised when a subprocess command fails."""

    def __init__(
        self,
        cmd: Sequence[str],
        returncode: int,
        output: str | None = None,
    ) -> None:
        self.cmd = cmd
        self.returncode = returncode
        self.output = output
        cmd_str = " ".join(cmd)
        self.message = f"Command failed (exit {returncode}): {cmd_str}"
        if output:
            self.message += f"\n{output}"
        super().__init__()


class GitError(ScriptError):
    """Raised when a git operation fails."""

    def __init__(self, operation: str, details: str | None = None) -> None:
        self.operation = operation
        self.details = details
        self.message = f"Git operation failed: {operation}"
        if details:
            self.message += f"\n{details}"
        super().__init__()
