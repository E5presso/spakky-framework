"""Tests for SQLAlchemy package metadata."""

from pathlib import Path
import tomllib


def test_base_dependencies_include_pydantic_settings_for_config_import() -> None:
    """Base package install includes SQLAlchemyConnectionConfig runtime dependency."""
    pyproject = Path(__file__).parents[2] / "pyproject.toml"

    metadata = tomllib.loads(pyproject.read_text(encoding="utf-8"))

    assert any(
        dependency.startswith("pydantic-settings")
        for dependency in metadata["project"]["dependencies"]
    )
