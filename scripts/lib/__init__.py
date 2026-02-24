"""Spakky workspace scripts library.

This package provides shared functionality for all workspace scripts:
- Configuration constants
- Error classes
- Data models
- Workspace and package discovery
- Git operations
- Process execution
- Console output helpers
"""

from __future__ import annotations

# Configuration
from lib.config import WORKSPACE_ROOT

# Console output
from lib.console import (
    console,
    err_console,
    exit_with_error,
    print_error,
    print_header,
    print_info,
    print_success,
    print_warning,
)

# Error classes
from lib.errors import (
    CommandError,
    GitError,
    PackageNotFoundError,
    PyprojectNotFoundError,
    ScriptError,
    WorkspaceMembersNotFoundError,
)

# Git operations
from lib.git import (
    get_changed_files_between,
    get_changed_packages,
    get_files_to_push,
    get_staged_files,
    get_upstream_branch,
)

# Data models
from lib.models import PackageInfo

# Process execution
from lib.process import run_command, run_streaming

# Workspace functions
from lib.workspace import (
    get_all_packages,
    get_package_by_name,
    get_package_by_path,
    get_package_info,
    get_workspace_members,
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
