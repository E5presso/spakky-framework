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

    Writes directly to /dev/tty (Unix) or CON (Windows) to bypass
    any stdout/stderr capturing by pre-commit hooks.

    Args:
        cmd: Command and arguments to run.
        cwd: Working directory for the command.
        env: Additional environment variables.

    Returns:
        Exit code of the command.
    """
    import sys
    import threading
    from io import BufferedWriter

    process_env = os.environ.copy()
    process_env["PYTHONUNBUFFERED"] = "1"
    process_env["FORCE_COLOR"] = "1"
    if env:
        process_env.update(env)

    # Try to open terminal directly to bypass pre-commit capturing
    tty_file: BufferedWriter | None = None
    try:
        if sys.platform == "win32":
            tty_file = open("CON", "wb")  # noqa: SIM115
        else:
            tty_file = open("/dev/tty", "wb")  # noqa: SIM115
    except OSError:
        # No TTY available (e.g., CI environment), fall back to stdout
        tty_file = None

    output_dest = tty_file if tty_file else sys.stdout.buffer

    process = subprocess.Popen(
        list(cmd),
        cwd=cwd or WORKSPACE_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # Merge stderr into stdout
        env=process_env,
    )

    def stream_reader() -> None:
        """Read from process stdout and write to terminal in real-time."""
        assert process.stdout is not None
        while True:
            chunk = process.stdout.read(1)
            if not chunk:
                break
            output_dest.write(chunk)
            output_dest.flush()

    assert process.stdout is not None

    reader_thread = threading.Thread(target=stream_reader)
    reader_thread.start()

    process.wait()
    reader_thread.join()

    if tty_file:
        tty_file.close()

    return process.returncode
