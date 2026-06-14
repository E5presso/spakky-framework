"""Unit tests for SQLAlchemy outbox contribution initialization."""

import os
from collections.abc import Generator
from unittest.mock import MagicMock

import pytest

from spakky.plugins.sqlalchemy.contributions.outbox import initialize
from spakky.plugins.sqlalchemy.outbox.storage import (
    AsyncSqlAlchemyOutboxStorage,
    SqlAlchemyOutboxStorage,
)
from spakky.plugins.sqlalchemy.outbox.table import OutboxMessageTable

_ENV_KEYS = (
    "SPAKKY_SQLALCHEMY__CONNECTION_STRING",
    "SPAKKY_SQLALCHEMY__SUPPORT_ASYNC_MODE",
)


@pytest.fixture(name="mock_app")
def mock_app_fixture() -> MagicMock:
    """Create a mock SpakkyApplication for testing."""
    return MagicMock()


@pytest.fixture(autouse=True)
def clean_env() -> Generator[None, None, None]:
    """Save and restore environment variables around each test."""
    saved = {k: os.environ.get(k) for k in _ENV_KEYS}
    os.environ["SPAKKY_SQLALCHEMY__CONNECTION_STRING"] = (
        "postgresql+psycopg://test:test@localhost/test"
    )
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_outbox_contribution_with_async_support_expect_all_pods_registered(
    mock_app: MagicMock,
) -> None:
    """support_async_mode가 True일 때 outbox 동기+비동기 Pod 등록을 검증한다."""
    os.environ["SPAKKY_SQLALCHEMY__SUPPORT_ASYNC_MODE"] = "true"

    initialize(mock_app)

    added_types = [call.args[0] for call in mock_app.add.call_args_list]
    assert OutboxMessageTable in added_types
    assert SqlAlchemyOutboxStorage in added_types
    assert AsyncSqlAlchemyOutboxStorage in added_types
    assert mock_app.add.call_count == 3


def test_outbox_contribution_without_async_support_expect_sync_pods_only(
    mock_app: MagicMock,
) -> None:
    """support_async_mode가 False일 때 outbox 동기 Pod만 등록되는지 검증한다."""
    os.environ["SPAKKY_SQLALCHEMY__SUPPORT_ASYNC_MODE"] = "false"

    initialize(mock_app)

    added_types = [call.args[0] for call in mock_app.add.call_args_list]
    assert OutboxMessageTable in added_types
    assert SqlAlchemyOutboxStorage in added_types
    assert AsyncSqlAlchemyOutboxStorage not in added_types
    assert mock_app.add.call_count == 2
