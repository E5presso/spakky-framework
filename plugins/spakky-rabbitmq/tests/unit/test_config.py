"""Tests for RabbitMQ configuration module.

This module contains tests for the RabbitMQ connection configuration,
including environment variable loading and property generation.
"""

from os import environ
from typing import Any, Generator

import pytest

from spakky.plugins.rabbitmq.common.config import RabbitMQConnectionConfig
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
    """Test that RabbitMQConnectionConfig loads values from environment variables."""
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
    """Test that RabbitMQConnectionConfig correctly handles SSL enabled."""
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
    """Test that protocol returns 'amqp' when SSL is disabled."""
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}USE_SSL"] = "false"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}HOST"] = "localhost"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}PORT"] = "5672"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}USER"] = "guest"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}PASSWORD"] = "guest"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}EXCHANGE_NAME"] = "test"

    config = RabbitMQConnectionConfig()

    assert config.protocol == "amqp"


def test_rabbitmq_config_connection_string_without_ssl(clean_env: None) -> None:
    """Test that connection_string is correctly generated without SSL."""
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}USE_SSL"] = "false"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}HOST"] = "localhost"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}PORT"] = "5672"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}USER"] = "myuser"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}PASSWORD"] = "mypassword"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}EXCHANGE_NAME"] = "test"

    config = RabbitMQConnectionConfig()

    assert config.connection_string == "amqp://myuser:mypassword@localhost:5672"


def test_rabbitmq_config_connection_string_with_ssl(clean_env: None) -> None:
    """Test that connection_string is correctly generated with SSL."""
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


def test_rabbitmq_config_exchange_name_is_required(clean_env: None) -> None:
    """Test that RabbitMQConnectionConfig requires exchange_name field."""
    from pydantic import ValidationError

    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}USE_SSL"] = "false"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}HOST"] = "localhost"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}PORT"] = "5672"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}USER"] = "guest"
    environ[f"{RABBITMQ_CONFIG_ENV_PREFIX}PASSWORD"] = "guest"
    # EXCHANGE_NAME is not set - should raise ValidationError

    with pytest.raises(ValidationError):
        RabbitMQConnectionConfig()


def test_rabbitmq_config_env_prefix_is_correct() -> None:
    """Test that the environment variable prefix follows the correct format."""
    assert RABBITMQ_CONFIG_ENV_PREFIX == "SPAKKY_RABBITMQ__"
    assert RABBITMQ_CONFIG_ENV_PREFIX.startswith("SPAKKY_")
    assert RABBITMQ_CONFIG_ENV_PREFIX.endswith("__")
