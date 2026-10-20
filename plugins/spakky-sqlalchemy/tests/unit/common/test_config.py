"""접속 설정과 Data 공통 실행 모드의 소유권을 검증한다."""

import pytest
from spakky.data.config import DataConfig

from spakky.plugins.sqlalchemy.common.config import SQLAlchemyConnectionConfig


def test_connection_config_common_async_mode_expect_data_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DB 설정은 SQLAlchemy가 읽고 실행 모드는 Data만 소유한다."""
    monkeypatch.setenv(
        "SPAKKY_SQLALCHEMY__CONNECTION_STRING", "sqlite+pysqlite:///:memory:"
    )
    monkeypatch.setenv("SPAKKY_SQLALCHEMY__POOL_SIZE", "3")
    monkeypatch.setenv("SPAKKY_SQLALCHEMY__SUPPORT_ASYNC_MODE", "true")
    monkeypatch.setenv("SPAKKY_DATA__SUPPORT_ASYNC_MODE", "false")
    config = SQLAlchemyConnectionConfig()
    assert config.connection_string == "sqlite+pysqlite:///:memory:"
    assert config.pool_size == 3
    assert "support_async_mode" not in SQLAlchemyConnectionConfig.model_fields
    assert DataConfig().support_async_mode is False
