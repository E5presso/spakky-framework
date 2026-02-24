"""Backward compatibility layer for Spakky workspace scripts.

This module re-exports all symbols from the lib package for backward
compatibility with existing scripts that import from 'common'.

New code should import directly from 'lib' or its submodules:
    from lib import WORKSPACE_ROOT, get_all_packages
    from lib.errors import ScriptError
    from lib.console import print_success
"""

from __future__ import annotations

# Re-export everything from lib for backward compatibility
from lib import (
    # Config
    WORKSPACE_ROOT,
    # Errors
    CommandError,
    GitError,
    # Models
    PackageInfo,
    PackageNotFoundError,
    PyprojectNotFoundError,
    ScriptError,
    WorkspaceMembersNotFoundError,
    # Console
    console,
    err_console,
    exit_with_error,
    # Workspace
    get_all_packages,
    # Git
    get_changed_files_between,
    get_changed_packages,
    get_files_to_push,
    get_package_by_name,
    get_package_by_path,
    get_package_info,
    get_staged_files,
    get_upstream_branch,
    get_workspace_members,
    print_error,
    print_header,
    print_info,
    print_success,
    print_warning,
    # Process
    run_command,
    run_streaming,
)

__all__ = [
    # Config
    "WORKSPACE_ROOT",
    # Console
    "console",
    "err_console",
    "exit_with_error",
    "print_error",
    "print_header",
    "print_info",
    "print_success",
    "print_warning",
    # Errors
    "CommandError",
    "GitError",
    "PackageNotFoundError",
    "PyprojectNotFoundError",
    "ScriptError",
    "WorkspaceMembersNotFoundError",
    # Git
    "get_changed_files_between",
    "get_changed_packages",
    "get_files_to_push",
    "get_staged_files",
    "get_upstream_branch",
    # Models
    "PackageInfo",
    # Process
    "run_command",
    "run_streaming",
    # Workspace
    "get_all_packages",
    "get_package_by_name",
    "get_package_by_path",
    "get_package_info",
    "get_workspace_members",
]
