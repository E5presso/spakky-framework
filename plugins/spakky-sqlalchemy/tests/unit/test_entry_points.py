"""Tests for SQLAlchemy plugin entry point metadata."""

from importlib.metadata import entry_points


def test_sqlalchemy_outbox_contribution_entry_point_is_declared() -> None:
    """SQLAlchemy outbox contribution entry point metadata를 검증한다."""
    contribution_entry_points = entry_points(group="spakky.contributions.spakky.outbox")

    assert any(
        entry_point.name == "spakky-sqlalchemy"
        and entry_point.value
        == "spakky.plugins.sqlalchemy.contributions.outbox:initialize"
        for entry_point in contribution_entry_points
    )
