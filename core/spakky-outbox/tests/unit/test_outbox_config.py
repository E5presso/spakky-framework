"""Tests for OutboxConfig."""

import os

from spakky.outbox.common.config import OutboxConfig


def test_outbox_config_default_values() -> None:
    """OutboxConfig가 기본값으로 올바르게 초기화되는지 검증한다."""
    config = OutboxConfig()

    assert config.polling_interval_seconds == 1.0
    assert config.batch_size == 100
    assert config.max_retry_count == 5


def test_outbox_config_from_environment_variables() -> None:
    """OutboxConfig가 환경변수에서 설정값을 로드하는지 검증한다."""
    os.environ["SPAKKY_OUTBOX__POLLING_INTERVAL_SECONDS"] = "2.5"
    os.environ["SPAKKY_OUTBOX__BATCH_SIZE"] = "50"
    os.environ["SPAKKY_OUTBOX__MAX_RETRY_COUNT"] = "10"
    try:
        config = OutboxConfig()

        assert config.polling_interval_seconds == 2.5
        assert config.batch_size == 50
        assert config.max_retry_count == 10
    finally:
        del os.environ["SPAKKY_OUTBOX__POLLING_INTERVAL_SECONDS"]
        del os.environ["SPAKKY_OUTBOX__BATCH_SIZE"]
        del os.environ["SPAKKY_OUTBOX__MAX_RETRY_COUNT"]
