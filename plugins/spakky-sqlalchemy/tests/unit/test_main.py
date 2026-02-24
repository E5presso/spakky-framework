"""Unit tests for main.py plugin initialization."""

import os
from unittest.mock import MagicMock

import pytest

from spakky.plugins.sqlalchemy.common.config import SQLAlchemyConnectionConfig
from spakky.plugins.sqlalchemy.main import initialize
from spakky.plugins.sqlalchemy.orm.schema_registry import SchemaRegistry
from spakky.plugins.sqlalchemy.persistency.connection_manager import (
    AsyncConnectionManager,
    ConnectionManager,
)
from spakky.plugins.sqlalchemy.persistency.session_manager import (
    AsyncSessionManager,
    SessionManager,
)
from spakky.plugins.sqlalchemy.persistency.transaction import (
    AsyncTransaction,
    Transaction,
)


@pytest.fixture(name="mock_app")
def mock_app_fixture() -> MagicMock:
    """Create a mock SpakkyApplication for testing.

    Returns:
        MagicMock instance simulating SpakkyApplication.
    """
    return MagicMock()


@pytest.fixture(name="setup_env")
def setup_env_fixture() -> None:
    """Set up required environment variables for SQLAlchemyConnectionConfig."""
    os.environ["SPAKKY_SQLALCHEMY__CONNECTION_STRING"] = (
        "postgresql+psycopg://test:test@localhost/test"
    )


def test_initialize_with_async_support_expect_all_pods_registered(
    mock_app: MagicMock,
    setup_env: None,
) -> None:
    """support_async_mode가 True일 때 모든 Pod(동기+비동기)이 등록되는지 검증한다."""
    os.environ["SPAKKY_SQLALCHEMY__SUPPORT_ASYNC_MODE"] = "true"

    initialize(mock_app)

    added_types = [call.args[0] for call in mock_app.add.call_args_list]
    assert SQLAlchemyConnectionConfig in added_types
    assert SchemaRegistry in added_types
    assert ConnectionManager in added_types
    assert SessionManager in added_types
    assert Transaction in added_types
    assert AsyncConnectionManager in added_types
    assert AsyncSessionManager in added_types
    assert AsyncTransaction in added_types
    assert mock_app.add.call_count == 8


def test_initialize_without_async_support_expect_sync_pods_only(
    mock_app: MagicMock,
    setup_env: None,
) -> None:
    """support_async_mode가 False일 때 동기 Pod만 등록되는지 검증한다."""
    os.environ["SPAKKY_SQLALCHEMY__SUPPORT_ASYNC_MODE"] = "false"

    initialize(mock_app)

    added_types = [call.args[0] for call in mock_app.add.call_args_list]
    assert SQLAlchemyConnectionConfig in added_types
    assert SchemaRegistry in added_types
    assert ConnectionManager in added_types
    assert SessionManager in added_types
    assert Transaction in added_types
    assert AsyncConnectionManager not in added_types
    assert AsyncSessionManager not in added_types
    assert AsyncTransaction not in added_types
    assert mock_app.add.call_count == 5


def test_initialize_default_async_mode_expect_async_pods_registered(
    mock_app: MagicMock,
    setup_env: None,
) -> None:
    """기본값(support_async_mode=True)일 때 비동기 Pod이 등록되는지 검증한다."""
    # Remove the key if it exists to use default
    os.environ.pop("SPAKKY_SQLALCHEMY__SUPPORT_ASYNC_MODE", None)

    initialize(mock_app)

    added_types = [call.args[0] for call in mock_app.add.call_args_list]
    assert AsyncConnectionManager in added_types
    assert AsyncSessionManager in added_types
    assert AsyncTransaction in added_types
