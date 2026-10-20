"""Data의 공통 동기 모드에서 SQLite 부팅과 실제 트랜잭션을 검증한다."""

from pathlib import Path

import pytest
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.stereotype.usecase import UseCase
from spakky.data.aspects.transactional import AsyncTransactionalAspect, transactional
from spakky.data.config import DataConfig
from spakky.data.main import initialize as initialize_data
from sqlalchemy import URL, text

from spakky.plugins.sqlalchemy.common.config import SQLAlchemyConnectionConfig
from spakky.plugins.sqlalchemy.main import initialize as initialize_sqlalchemy
from spakky.plugins.sqlalchemy.persistency.connection_manager import (
    AsyncConnectionManager,
    ConnectionManager,
)
from spakky.plugins.sqlalchemy.persistency.session_manager import SessionManager
from spakky.plugins.sqlalchemy.persistency.transaction import AsyncTransaction


@UseCase()
class WriteProbeUseCase:
    """AOP가 연 실제 SQLite 트랜잭션에서 값을 저장한다."""

    def __init__(self, sessions: SessionManager) -> None:
        self.sessions = sessions

    @transactional
    def write(self, fail: bool) -> None:
        self.sessions.session.execute(text("INSERT INTO probe VALUES (1)"))
        if fail:
            raise RuntimeError("rollback probe")


@pytest.mark.parametrize("provider_first", [False, True])
@pytest.mark.parametrize("fail", [False, True])
def test_shared_sync_mode_sqlite_expect_start_and_atomic_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider_first: bool,
    fail: bool,
) -> None:
    """초기화 순서와 무관하게 비동기 Pod를 제외하고 SQLite commit·rollback을 수행한다."""
    monkeypatch.setenv("SPAKKY_DATA__SUPPORT_ASYNC_MODE", "false")
    monkeypatch.setenv("SPAKKY_SQLALCHEMY__SUPPORT_ASYNC_MODE", "true")
    monkeypatch.setenv(
        "SPAKKY_SQLALCHEMY__CONNECTION_STRING",
        URL.create(
            "sqlite+pysqlite", database=str(tmp_path / "probe.db")
        ).render_as_string(),
    )
    application = SpakkyApplication(ApplicationContext())
    if provider_first:
        initialize_sqlalchemy(application)
        initialize_data(application)
    else:
        initialize_data(application)
        initialize_sqlalchemy(application)
    application.add(WriteProbeUseCase).start()
    manager = application.container.get(ConnectionManager)
    try:
        assert application.container.get(DataConfig).support_async_mode is False
        assert "support_async_mode" not in SQLAlchemyConnectionConfig.model_fields
        assert not application.container.contains(AsyncTransactionalAspect)
        assert not application.container.contains(AsyncConnectionManager)
        assert not application.container.contains(AsyncTransaction)
        with manager.connection.begin() as connection:
            connection.execute(text("CREATE TABLE probe (value INTEGER NOT NULL)"))
        usecase = application.container.get(WriteProbeUseCase)
        if fail:
            with pytest.raises(RuntimeError, match="rollback probe"):
                usecase.write(fail=True)
        else:
            usecase.write(fail=False)
        with manager.connection.connect() as connection:
            assert connection.scalar(text("SELECT COUNT(*) FROM probe")) == (
                0 if fail else 1
            )
    finally:
        application.stop()
        manager.dispose()
