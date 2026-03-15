"""Tests for LoggingConfig — @Configuration Pod for logging settings."""

import logging

from spakky.plugins.logging.config import LogFormat, LoggingConfig


def test_logging_config_defaults_expect_sane_values() -> None:
    """LoggingConfig의 기본값이 합리적임을 검증한다."""
    config = LoggingConfig()

    assert config.level == logging.INFO
    assert config.format == LogFormat.TEXT
    assert config.date_format == "%Y-%m-%dT%H:%M:%S%z"
    assert config.package_levels == {}
    assert "password" in config.mask_keys
    assert "secret" in config.mask_keys
    assert "token" in config.mask_keys
    assert config.mask_replacement == "******"
    assert config.slow_threshold_ms == 1000.0
    assert config.max_result_length == 200


def test_logging_config_custom_values_expect_override() -> None:
    """LoggingConfig에 커스텀 값을 설정할 수 있음을 검증한다."""
    config = LoggingConfig()
    config.level = logging.DEBUG
    config.format = LogFormat.JSON
    config.slow_threshold_ms = 500.0
    config.max_result_length = 100
    config.mask_keys = ["api_key"]
    config.package_levels = {"spakky.core": logging.WARNING}

    assert config.level == logging.DEBUG
    assert config.format == LogFormat.JSON
    assert config.slow_threshold_ms == 500.0
    assert config.max_result_length == 100
    assert config.mask_keys == ["api_key"]
    assert config.package_levels == {"spakky.core": logging.WARNING}


def test_log_format_enum_values_expect_three_options() -> None:
    """LogFormat enum이 text, json, pretty 세 가지를 제공함을 검증한다."""
    assert LogFormat.TEXT.value == "text"
    assert LogFormat.JSON.value == "json"
    assert LogFormat.PRETTY.value == "pretty"
    assert len(LogFormat) == 3
