"""Unit tests for OutboxConfig."""

import os
from typing import Any, Generator

import pytest

from spakky.plugins.outbox.common.config import OutboxConfig
from spakky.plugins.outbox.common.constants import SPAKKY_OUTBOX_CONFIG_ENV_PREFIX


@pytest.fixture(name="clean_env")
def clean_environment_fixture() -> Generator[None, Any, None]:
    """Remove outbox env vars before test and restore after."""
    keys = [
        f"{SPAKKY_OUTBOX_CONFIG_ENV_PREFIX}POLLING_INTERVAL_SECONDS",
        f"{SPAKKY_OUTBOX_CONFIG_ENV_PREFIX}BATCH_SIZE",
        f"{SPAKKY_OUTBOX_CONFIG_ENV_PREFIX}MAX_RETRY_COUNT",
        f"{SPAKKY_OUTBOX_CONFIG_ENV_PREFIX}AUTO_CREATE_TABLE",
    ]
    saved: dict[str, str] = {}
    for key in keys:
        if key in os.environ:
            saved[key] = os.environ.pop(key)

    yield

    for key in keys:
        if key in os.environ:
            del os.environ[key]
    for key, value in saved.items():
        os.environ[key] = value


def test_outbox_config_default_values_expect_defaults_returned(
    clean_env: None,
) -> None:
    """기본값으로 OutboxConfig를 생성하면 각 필드가 기본값을 반환하는지 검증한다."""
    config = OutboxConfig()

    assert config.polling_interval_seconds == 1.0
    assert config.batch_size == 100
    assert config.max_retry_count == 5
    assert config.auto_create_table is True


def test_outbox_config_loads_from_environment_variables(clean_env: None) -> None:
    """환경 변수에서 OutboxConfig 값을 올바르게 로드하는지 검증한다."""
    os.environ[f"{SPAKKY_OUTBOX_CONFIG_ENV_PREFIX}POLLING_INTERVAL_SECONDS"] = "2.5"
    os.environ[f"{SPAKKY_OUTBOX_CONFIG_ENV_PREFIX}BATCH_SIZE"] = "50"
    os.environ[f"{SPAKKY_OUTBOX_CONFIG_ENV_PREFIX}MAX_RETRY_COUNT"] = "3"
    os.environ[f"{SPAKKY_OUTBOX_CONFIG_ENV_PREFIX}AUTO_CREATE_TABLE"] = "false"

    config = OutboxConfig()

    assert config.polling_interval_seconds == 2.5
    assert config.batch_size == 50
    assert config.max_retry_count == 3
    assert config.auto_create_table is False


def test_outbox_config_env_prefix_is_correct() -> None:
    """환경 변수 접두사가 올바른 형식을 따르는지 검증한다."""
    assert SPAKKY_OUTBOX_CONFIG_ENV_PREFIX == "SPAKKY_OUTBOX__"
    assert SPAKKY_OUTBOX_CONFIG_ENV_PREFIX.startswith("SPAKKY_")
    assert SPAKKY_OUTBOX_CONFIG_ENV_PREFIX.endswith("__")
