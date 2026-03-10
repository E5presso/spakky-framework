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
    """KafkaConnectionConfig가 환경 변수에서 값을 올바르게 로드하는지 검증한다."""
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
    """KafkaConnectionConfig가 SASL 인증 설정을 올바르게 처리하는지 검증한다."""
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
    """KafkaConnectionConfig가 올바른 기본값을 사용하는지 검증한다."""
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
    """configuration_dict가 올바른 기본 설정 딕셔너리를 반환하는지 검증한다."""
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
    """SASL 설정이 구성된 경우 configuration_dict에 SASL 설정이 포함되는지 검증한다."""
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
    """모든 AutoOffsetResetType 열거형 값이 올바르게 동작하는지 검증한다."""
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}GROUP_ID"] = "test-group"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CLIENT_ID"] = "test-client"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS"] = "localhost:9092"

    for reset_type in AutoOffsetResetType:
        environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}AUTO_OFFSET_RESET"] = reset_type.value
        config = KafkaConnectionConfig()
        assert config.auto_offset_reset == reset_type
        assert config.configuration_dict["auto.offset.reset"] == reset_type.value


def test_kafka_config_with_custom_partitions_and_replication(clean_env: None) -> None:
    """사용자 지정 파티션 수와 복제 팩터가 올바르게 로드되는지 검증한다."""
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}GROUP_ID"] = "test-group"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CLIENT_ID"] = "test-client"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS"] = "localhost:9092"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}NUMBER_OF_PARTITIONS"] = "3"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}REPLICATION_FACTOR"] = "2"

    config = KafkaConnectionConfig()

    assert config.number_of_partitions == 3
    assert config.replication_factor == 2


def test_kafka_config_env_prefix_is_correct() -> None:
    """환경 변수 접두사가 올바른 형식을 따르는지 검증한다."""
    assert SPAKKY_KAFKA_CONFIG_ENV_PREFIX == "SPAKKY_KAFKA__"
    assert SPAKKY_KAFKA_CONFIG_ENV_PREFIX.startswith("SPAKKY_")
    assert SPAKKY_KAFKA_CONFIG_ENV_PREFIX.endswith("__")


def test_auto_offset_reset_enum_values() -> None:
    """AutoOffsetResetType 열거형이 올바른 값을 갖는지 검증한다."""
    assert AutoOffsetResetType.EARLIEST.value == "earliest"
    assert AutoOffsetResetType.LATEST.value == "latest"
    assert AutoOffsetResetType.NONE.value == "none"
