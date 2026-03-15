"""Unit tests for main.py plugin initialization."""

import os
from typing import Generator
from unittest.mock import MagicMock

import pytest

import spakky.plugins.sqlalchemy.main as main_module
from spakky.plugins.sqlalchemy.common.config import SQLAlchemyConnectionConfig
from spakky.plugins.sqlalchemy.main import initialize
from spakky.plugins.sqlalchemy.orm.schema_registry import SchemaRegistry
from spakky.plugins.sqlalchemy.outbox.storage import (
    AsyncSqlAlchemyOutboxStorage,
    SqlAlchemyOutboxStorage,
)
from spakky.plugins.sqlalchemy.outbox.table import OutboxMessageTable
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

_ENV_KEYS = (
    "SPAKKY_SQLALCHEMY__CONNECTION_STRING",
    "SPAKKY_SQLALCHEMY__SUPPORT_ASYNC_MODE",
)


@pytest.fixture(name="mock_app")
def mock_app_fixture() -> MagicMock:
    """Create a mock SpakkyApplication for testing.

    Returns:
        MagicMock instance simulating SpakkyApplication.
    """
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


def test_initialize_with_async_support_expect_all_pods_registered(
    mock_app: MagicMock,
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
    assert OutboxMessageTable in added_types
    assert SqlAlchemyOutboxStorage in added_types
    assert AsyncSqlAlchemyOutboxStorage in added_types
    assert mock_app.add.call_count == 11


def test_initialize_without_async_support_expect_sync_pods_only(
    mock_app: MagicMock,
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
    assert OutboxMessageTable in added_types
    assert SqlAlchemyOutboxStorage in added_types
    assert AsyncSqlAlchemyOutboxStorage not in added_types
    assert mock_app.add.call_count == 7


def test_initialize_default_async_mode_expect_async_pods_registered(
    mock_app: MagicMock,
) -> None:
    """기본값(support_async_mode=True)일 때 비동기 Pod이 등록되는지 검증한다."""
    # Remove the key if it exists to use default
    os.environ.pop("SPAKKY_SQLALCHEMY__SUPPORT_ASYNC_MODE", None)

    initialize(mock_app)

    added_types = [call.args[0] for call in mock_app.add.call_args_list]
    assert AsyncConnectionManager in added_types
    assert AsyncSessionManager in added_types
    assert AsyncTransaction in added_types


def test_initialize_without_outbox_expect_no_outbox_pods(
    mock_app: MagicMock,
) -> None:
    """spakky-outbox 미설치 환경에서 Outbox Pod이 등록되지 않는지 검증한다."""
    os.environ["SPAKKY_SQLALCHEMY__SUPPORT_ASYNC_MODE"] = "true"
    original = main_module._HAS_OUTBOX
    main_module._HAS_OUTBOX = False
    try:
        initialize(mock_app)
    finally:
        main_module._HAS_OUTBOX = original

    added_types = [call.args[0] for call in mock_app.add.call_args_list]
    assert OutboxMessageTable not in added_types
    assert SqlAlchemyOutboxStorage not in added_types
    assert AsyncSqlAlchemyOutboxStorage not in added_types
    assert mock_app.add.call_count == 8
