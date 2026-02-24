"""Process execution utilities for Spakky workspace scripts."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from lib.config import WORKSPACE_ROOT
from lib.errors import CommandError

if TYPE_CHECKING:
    from collections.abc import Sequence


def run_command(
    cmd: Sequence[str],
    *,
    cwd: Path | None = None,
    capture: bool = True,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Execute a shell command.

    Args:
        cmd: Command and arguments to run.
        cwd: Working directory for the command.
        capture: Whether to capture stdout/stderr.
        check: Whether to raise on non-zero exit code.
        env: Environment variables to set.

    Returns:
        CompletedProcess instance.

    Raises:
        CommandError: If check=True and command fails.
    """
    process_env = os.environ.copy()
    if env:
        process_env.update(env)

    result = subprocess.run(
        list(cmd),
        cwd=cwd or WORKSPACE_ROOT,
        text=True,
        capture_output=capture,
        env=process_env,
        check=False,
    )

    if check and result.returncode != 0:
        output = result.stderr.strip() or result.stdout.strip() if capture else None
        raise CommandError(list(cmd), result.returncode, output)

    return result


def run_streaming(
    cmd: Sequence[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> int:
    """Execute a command with streaming output to terminal.

    Args:
        cmd: Command and arguments to run.
        cwd: Working directory for the command.
        env: Additional environment variables.

    Returns:
        Exit code of the command.
    """
    process_env = os.environ.copy()
    process_env["PYTHONUNBUFFERED"] = "1"
    process_env["FORCE_COLOR"] = "1"
    if env:
        process_env.update(env)

    process = subprocess.Popen(
        list(cmd),
        cwd=cwd or WORKSPACE_ROOT,
        stdout=None,  # Inherit from parent
        stderr=None,  # Inherit from parent
        bufsize=0,
        env=process_env,
    )
    process.wait()
    return process.returncode
