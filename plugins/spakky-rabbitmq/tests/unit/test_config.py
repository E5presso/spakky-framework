"""Tests for RabbitMQ configuration module.

This module contains tests for the RabbitMQ connection configuration,
including environment variable loading and property generation.
"""

from os import environ
from typing import Any, Generator

import pytest

from spakky.plugins.rabbitmq.common.config import (
    RabbitMQAuthFailureAction,
    RabbitMQConnectionConfig,
)
from spakky.plugins.rabbitmq.common.constants import RABBITMQ_CONFIG_ENV_PREFIX


@pytest.fixture(name="clean_env")
def clean_environment_fixture() -> Generator[None, Any, None]:
    """Clean up RabbitMQ environment variables before and after test."""
    keys_to_remove = [
        f"{RABBITMQ_CONFIG_ENV_PREFIX}USE_SSL",
        f"{RABBITMQ_CONFIG_ENV_PREFIX}HOST",
        f"{RABBITMQ_CONFIG_ENV_PREFIX}PORT",
        f"{RABBITMQ_CONFIG_ENV_PREFIX}USER",
        f"{RABBITMQ_CONFIG_ENV_PREFIX}PASSWORD",
        f"{RABBITMQ_CONFIG_ENV_PREFIX}EXCHANGE_NAME",
        f"{RABBITMQ_CONFIG_ENV_PREFIX}AUTH_CHALLENGE_ACTION",
        f"{RABBITMQ_CONFIG_ENV_PREFIX}AUTH_DENY_ACTION",
        f"{RABBITMQ_CONFIG_ENV_PREFIX}AUTH_ERROR_ACTION",
    ]
    original_values = {}
    for key in keys_to_remove:
        if key in environ:
            original_values[key] = environ.pop(key)

    yield

    for key in keys_to_remove:
        if key in environ:
            del environ[key]
    for key, value in original_values.items():
        environ[key] = value


def test_rabbitmq_config_loads_from_environment_variables(clean_env: None) -> None:
    """RabbitMQConnectionConfig가 환경 변수에서 값을 올바르게 로드하는지 검증한다."""
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}USE_SSL"] = "false"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}HOST"] = "test-host"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}PORT"] = "5672"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}USER"] = "test-user"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}PASSWORD"] = "test-password"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}EXCHANGE_NAME"] = "test-exchange"

    config = RabbitMQConnectionConfig()

    assert config.use_ssl is False
    assert config.host == "test-host"
    assert config.port == 5672
    assert config.user == "test-user"
    assert config.password == "test-password"
    assert config.exchange_name == "test-exchange"


def test_rabbitmq_config_with_ssl_enabled(clean_env: None) -> None:
    """RabbitMQConnectionConfig가 SSL 활성화 설정을 올바르게 처리하는지 검증한다."""
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}USE_SSL"] = "true"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}HOST"] = "secure-host"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}PORT"] = "5671"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}USER"] = "admin"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}PASSWORD"] = "secret"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}EXCHANGE_NAME"] = "secure-exchange"

    config = RabbitMQConnectionConfig()

    assert config.use_ssl is True
    assert config.protocol == "amqps"


def test_rabbitmq_config_protocol_without_ssl(clean_env: None) -> None:
    """SSL이 비활성화된 경우 protocol이 'amqp'를 반환하는지 검증한다."""
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}USE_SSL"] = "false"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}HOST"] = "localhost"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}PORT"] = "5672"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}USER"] = "guest"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}PASSWORD"] = "guest"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}EXCHANGE_NAME"] = "test"

    config = RabbitMQConnectionConfig()

    assert config.protocol == "amqp"


def test_rabbitmq_config_connection_string_without_ssl(clean_env: None) -> None:
    """SSL 없이 connection_string이 올바르게 생성되는지 검증한다."""
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}USE_SSL"] = "false"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}HOST"] = "localhost"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}PORT"] = "5672"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}USER"] = "myuser"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}PASSWORD"] = "mypassword"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}EXCHANGE_NAME"] = "test"

    config = RabbitMQConnectionConfig()

    assert config.connection_string == "amqp://myuser:mypassword@localhost:5672"


def test_rabbitmq_config_connection_string_with_ssl(clean_env: None) -> None:
    """SSL을 사용할 때 connection_string이 올바르게 생성되는지 검증한다."""
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}USE_SSL"] = "true"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}HOST"] = "secure.rabbitmq.com"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}PORT"] = "5671"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}USER"] = "admin"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}PASSWORD"] = "secret123"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}EXCHANGE_NAME"] = "secure"

    config = RabbitMQConnectionConfig()

    assert (
        config.connection_string == "amqps://admin:secret123@secure.rabbitmq.com:5671"
    )


def test_rabbitmq_config_exchange_name_is_optional(clean_env: None) -> None:
    """RabbitMQConnectionConfig에 exchange_name 필드가 선택적임을 검증한다."""
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}USE_SSL"] = "false"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}HOST"] = "localhost"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}PORT"] = "5672"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}USER"] = "guest"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}PASSWORD"] = "guest"
    # EXCHANGE_NAME is not set - should default to None

    config = RabbitMQConnectionConfig()

    assert config.exchange_name is None


def test_rabbitmq_config_auth_failure_actions_default_avoid_poison_loop(
    clean_env: None,
) -> None:
    """인증 실패 ack/nack 기본값이 poison-loop를 피하고 ERROR만 재시도함을 검증한다."""
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}USE_SSL"] = "false"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}HOST"] = "localhost"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}PORT"] = "5672"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}USER"] = "guest"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}PASSWORD"] = "guest"

    config = RabbitMQConnectionConfig()

    assert config.auth_challenge_action is RabbitMQAuthFailureAction.ACK
    assert config.auth_deny_action is RabbitMQAuthFailureAction.ACK
    assert config.auth_error_action is RabbitMQAuthFailureAction.NACK_REQUEUE


def test_rabbitmq_config_auth_failure_actions_load_from_environment(
    clean_env: None,
) -> None:
    """환경 변수로 인증 실패 ack/nack 정책을 구성할 수 있음을 검증한다."""
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}USE_SSL"] = "false"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}HOST"] = "localhost"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}PORT"] = "5672"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}USER"] = "guest"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}PASSWORD"] = "guest"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}AUTH_CHALLENGE_ACTION"] = "nack_drop"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}AUTH_DENY_ACTION"] = "nack_drop"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}AUTH_ERROR_ACTION"] = "nack_requeue"

    config = RabbitMQConnectionConfig()

    assert config.auth_challenge_action is RabbitMQAuthFailureAction.NACK_DROP
    assert config.auth_deny_action is RabbitMQAuthFailureAction.NACK_DROP
    assert config.auth_error_action is RabbitMQAuthFailureAction.NACK_REQUEUE


def test_rabbitmq_config_env_prefix_is_correct() -> None:
    """환경 변수 접두사가 올바른 형식을 따르는지 검증한다."""
    assert RABBITMQ_CONFIG_ENV_PREFIX == "SPAKKY_RABBITMQ__"
    assert RABBITMQ_CONFIG_ENV_PREFIX.startswith("SPAKKY_")
    assert RABBITMQ_CONFIG_ENV_PREFIX.endswith("__")
