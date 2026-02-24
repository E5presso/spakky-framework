"""Data models for Spakky workspace scripts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lib.config import WORKSPACE_ROOT


@dataclass
class PackageInfo:
    """Information about a workspace package."""

    name: str
    """Package name (e.g., 'spakky-fastapi')."""

    path: Path
    """Relative path from workspace root (e.g., 'plugins/spakky-fastapi')."""

    python_name: str
    """Python import name (e.g., 'spakky.plugins.fastapi')."""

    @property
    def full_path(self) -> Path:
        """Absolute path to the package directory."""
        return WORKSPACE_ROOT / self.path

    @property
    def has_precommit_config(self) -> bool:
        """Check if the package has a .pre-commit-config.yaml file."""
        return (self.full_path / ".pre-commit-config.yaml").exists()
