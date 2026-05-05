"""Tests for SQLAlchemy plugin entry point metadata."""

from importlib.metadata import entry_points

import pytest
import spakky.outbox
import spakky.plugins.sqlalchemy
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.plugins.sqlalchemy.orm.table import Table
from spakky.plugins.sqlalchemy.outbox.storage import (
    AsyncSqlAlchemyOutboxStorage,
    SqlAlchemyOutboxStorage,
)
from spakky.plugins.sqlalchemy.outbox.table import OutboxMessageTable


def test_sqlalchemy_outbox_contribution_entry_point_is_declared() -> None:
    """SQLAlchemy outbox contribution entry point metadata를 검증한다."""
    contribution_entry_points = entry_points(group="spakky.contributions.spakky.outbox")

    assert any(
        entry_point.name == "spakky-sqlalchemy"
        and entry_point.value
        == "spakky.plugins.sqlalchemy.contributions.outbox:initialize"
        for entry_point in contribution_entry_points
    )


def test_load_plugins_with_outbox_and_sqlalchemy_expect_outbox_contribution_registered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """spakky-outbox active 조합에서 SQLAlchemy contribution 등록을 검증한다."""
    monkeypatch.setenv(
        "SPAKKY_SQLALCHEMY__CONNECTION_STRING",
        "postgresql+psycopg://test:test@localhost/test",
    )

    app = SpakkyApplication(ApplicationContext()).load_plugins(
        include={
            spakky.outbox.PLUGIN_NAME,
            spakky.plugins.sqlalchemy.PLUGIN_NAME,
        }
    )
    added_types = {pod.type_ for pod in app.container.pods.values()}

    assert app.application_context.contains_tag(Table.get(OutboxMessageTable))
    assert SqlAlchemyOutboxStorage in added_types
    assert AsyncSqlAlchemyOutboxStorage in added_types


def test_load_plugins_with_sqlalchemy_only_expect_outbox_contribution_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """spakky-outbox 비활성 조합에서는 SQLAlchemy outbox Pod을 등록하지 않는다."""
    monkeypatch.setenv(
        "SPAKKY_SQLALCHEMY__CONNECTION_STRING",
        "postgresql+psycopg://test:test@localhost/test",
    )

    app = SpakkyApplication(ApplicationContext()).load_plugins(
        include={spakky.plugins.sqlalchemy.PLUGIN_NAME}
    )
    added_types = {pod.type_ for pod in app.container.pods.values()}

    assert not app.application_context.contains_tag(Table.get(OutboxMessageTable))
    assert SqlAlchemyOutboxStorage not in added_types
    assert AsyncSqlAlchemyOutboxStorage not in added_types
