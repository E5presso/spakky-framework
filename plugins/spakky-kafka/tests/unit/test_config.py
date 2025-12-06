"""Tests for Kafka configuration module.

This module contains tests for the Kafka connection configuration,
including environment variable loading and configuration dictionary generation.
"""

from os import environ
from typing import Any, Generator

import pytest

from spakky.plugins.kafka.common.config import (
    AutoOffsetResetType,
    KafkaConnectionConfig,
)
from spakky.plugins.kafka.common.constants import SPAKKY_KAFKA_CONFIG_ENV_PREFIX


@pytest.fixture(name="clean_env")
def clean_environment_fixture() -> Generator[None, Any, None]:
    """Clean up Kafka environment variables before and after test."""
    keys_to_remove = [
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}GROUP_ID",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CLIENT_ID",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SECURITY_PROTOCOL",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SASL_MECHANISM",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SASL_USERNAME",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SASL_PASSWORD",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}NUMBER_OF_PARTITIONS",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}REPLICATION_FACTOR",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}AUTO_OFFSET_RESET",
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


def test_kafka_config_loads_from_environment_variables(clean_env: None) -> None:
    """Test that KafkaConnectionConfig loads values from environment variables."""
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}GROUP_ID"] = "my-group"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CLIENT_ID"] = "my-client"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS"] = "localhost:9092"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}AUTO_OFFSET_RESET"] = "earliest"

    config = KafkaConnectionConfig()

    assert config.group_id == "my-group"
    assert config.client_id == "my-client"
    assert config.bootstrap_servers == "localhost:9092"
    assert config.auto_offset_reset == AutoOffsetResetType.EARLIEST


def test_kafka_config_with_sasl_authentication(clean_env: None) -> None:
    """Test that KafkaConnectionConfig correctly handles SASL authentication."""
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}GROUP_ID"] = "secure-group"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CLIENT_ID"] = "secure-client"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS"] = (
        "kafka.example.com:9093"
    )
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SECURITY_PROTOCOL"] = "SASL_SSL"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SASL_MECHANISM"] = "PLAIN"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SASL_USERNAME"] = "admin"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SASL_PASSWORD"] = "secret"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}AUTO_OFFSET_RESET"] = "latest"

    config = KafkaConnectionConfig()

    assert config.security_protocol == "SASL_SSL"
    assert config.sasl_mechanism == "PLAIN"
    assert config.sasl_username == "admin"
    assert config.sasl_password == "secret"


def test_kafka_config_default_values(clean_env: None) -> None:
    """Test that KafkaConnectionConfig uses correct default values."""
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}GROUP_ID"] = "test-group"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CLIENT_ID"] = "test-client"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS"] = "localhost:9092"

    config = KafkaConnectionConfig()

    assert config.security_protocol is None
    assert config.sasl_mechanism is None
    assert config.sasl_username is None
    assert config.sasl_password is None
    assert config.number_of_partitions == 1
    assert config.replication_factor == 1
    assert config.auto_offset_reset == AutoOffsetResetType.EARLIEST


def test_kafka_config_configuration_dict_basic(clean_env: None) -> None:
    """Test that configuration_dict returns correct basic configuration."""
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}GROUP_ID"] = "my-group"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CLIENT_ID"] = "my-client"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS"] = "localhost:9092"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}AUTO_OFFSET_RESET"] = "earliest"

    config = KafkaConnectionConfig()
    config_dict = config.configuration_dict

    assert config_dict["group.id"] == "my-group"
    assert config_dict["client.id"] == "my-client"
    assert config_dict["bootstrap.servers"] == "localhost:9092"
    assert config_dict["auto.offset.reset"] == "earliest"
    assert "security.protocol" not in config_dict
    assert "sasl.mechanism" not in config_dict
    assert "sasl.username" not in config_dict
    assert "sasl.password" not in config_dict


def test_kafka_config_configuration_dict_with_sasl(clean_env: None) -> None:
    """Test that configuration_dict includes SASL settings when configured."""
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}GROUP_ID"] = "secure-group"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CLIENT_ID"] = "secure-client"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS"] = (
        "kafka.example.com:9093"
    )
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SECURITY_PROTOCOL"] = "SASL_SSL"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SASL_MECHANISM"] = "SCRAM-SHA-256"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SASL_USERNAME"] = "kafka-user"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SASL_PASSWORD"] = "kafka-pass"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}AUTO_OFFSET_RESET"] = "latest"

    config = KafkaConnectionConfig()
    config_dict = config.configuration_dict

    assert config_dict["security.protocol"] == "SASL_SSL"
    assert config_dict["sasl.mechanism"] == "SCRAM-SHA-256"
    assert config_dict["sasl.username"] == "kafka-user"
    assert config_dict["sasl.password"] == "kafka-pass"


def test_kafka_config_auto_offset_reset_values(clean_env: None) -> None:
    """Test that all AutoOffsetResetType values work correctly."""
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}GROUP_ID"] = "test-group"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CLIENT_ID"] = "test-client"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS"] = "localhost:9092"

    for reset_type in AutoOffsetResetType:
        environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}AUTO_OFFSET_RESET"] = reset_type.value
        config = KafkaConnectionConfig()
        assert config.auto_offset_reset == reset_type
        assert config.configuration_dict["auto.offset.reset"] == reset_type.value


def test_kafka_config_with_custom_partitions_and_replication(clean_env: None) -> None:
    """Test that custom partitions and replication factor are correctly loaded."""
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}GROUP_ID"] = "test-group"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CLIENT_ID"] = "test-client"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS"] = "localhost:9092"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}NUMBER_OF_PARTITIONS"] = "3"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}REPLICATION_FACTOR"] = "2"

    config = KafkaConnectionConfig()

    assert config.number_of_partitions == 3
    assert config.replication_factor == 2


def test_kafka_config_env_prefix_is_correct() -> None:
    """Test that the environment variable prefix follows the correct format."""
    assert SPAKKY_KAFKA_CONFIG_ENV_PREFIX == "SPAKKY_KAFKA__"
    assert SPAKKY_KAFKA_CONFIG_ENV_PREFIX.startswith("SPAKKY_")
    assert SPAKKY_KAFKA_CONFIG_ENV_PREFIX.endswith("__")


def test_auto_offset_reset_enum_values() -> None:
    """Test that AutoOffsetResetType enum has correct values."""
    assert AutoOffsetResetType.EARLIEST.value == "earliest"
    assert AutoOffsetResetType.LATEST.value == "latest"
    assert AutoOffsetResetType.NONE.value == "none"
