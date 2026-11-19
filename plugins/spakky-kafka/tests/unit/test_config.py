"""Tests for Kafka configuration module.

This module contains tests for the Kafka connection configuration,
including environment variable loading and configuration dictionary generation.
"""

from os import environ
from ssl import CERT_REQUIRED, SSLContext, SSLError
from unittest.mock import MagicMock, patch
from pathlib import Path
from typing import Any
from collections.abc import Generator

import pytest
from pydantic import ValidationError

from spakky.plugins.kafka.common.config import (
    AutoOffsetResetType,
    KafkaConnectionConfig,
)
from spakky.event.retry import RetryMode, RetryPolicy

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
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SSL_CA_LOCATION",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SSL_CERTIFICATE_LOCATION",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SSL_KEY_LOCATION",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}NUMBER_OF_PARTITIONS",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}REPLICATION_FACTOR",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}AUTO_OFFSET_RESET",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}DEAD_LETTER_TOPIC_SUFFIX",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}RETRY_TOPIC_SUFFIX",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}RETRY__MAX_ATTEMPTS",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}RETRY__INITIAL_INTERVAL",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}RETRY__MULTIPLIER",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}RETRY__MAX_INTERVAL",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}RETRY__MODE",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SUBSCRIBER_RETRY",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}REDRIVE_TIMEOUT",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}DEAD_LETTER_DELIVERY_TIMEOUT",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CONSUMER_OVERRIDES",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SUBSCRIBER_CONSUMER_OVERRIDES",
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
    assert config.dead_letter_topic_suffix == ".dlt"
    assert config.retry_topic_suffix == ".retry"
    assert config.retry == RetryPolicy()
    assert config.retry.max_attempts == 1
    assert config.retry.mode is RetryMode.BLOCKING
    assert config.redrive_timeout == 10.0
    assert config.dead_letter_delivery_timeout == 10.0


def test_kafka_config_connection_configuration_dict_basic(clean_env: None) -> None:
    """connection_configuration_dict가 클러스터 접속 설정만 담는지 검증한다."""
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}GROUP_ID"] = "my-group"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CLIENT_ID"] = "my-client"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS"] = "localhost:9092"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}AUTO_OFFSET_RESET"] = "earliest"

    config = KafkaConnectionConfig()
    config_dict = config.connection_configuration_dict

    assert config_dict["client.id"] == "my-client"
    assert config_dict["bootstrap.servers"] == "localhost:9092"
    assert "group.id" not in config_dict
    assert "auto.offset.reset" not in config_dict
    assert "security.protocol" not in config_dict
    assert "sasl.mechanism" not in config_dict
    assert "sasl.username" not in config_dict
    assert "sasl.password" not in config_dict


def test_kafka_config_producer_configuration_dict_expect_idempotent_delivery(
    clean_env: None,
) -> None:
    """producer_configuration_dict가 중복·재정렬을 막는 기본값을 고정하는지 검증한다."""
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}GROUP_ID"] = "my-group"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CLIENT_ID"] = "my-client"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS"] = "localhost:9092"

    config = KafkaConnectionConfig()
    config_dict = config.producer_configuration_dict

    assert config_dict["enable.idempotence"] is True
    assert config_dict["acks"] == "all"
    assert config_dict["client.id"] == "my-client"
    assert config_dict["bootstrap.servers"] == "localhost:9092"
    assert "group.id" not in config_dict
    assert "enable.auto.commit" not in config_dict


def test_kafka_config_consumer_configuration_dict_expect_manual_offset_commit(
    clean_env: None,
) -> None:
    """consumer_configuration_dict가 자동 커밋을 끄고 소비 그룹 설정을 담는지 검증한다."""
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}GROUP_ID"] = "my-group"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CLIENT_ID"] = "my-client"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS"] = "localhost:9092"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}AUTO_OFFSET_RESET"] = "earliest"

    config = KafkaConnectionConfig()
    config_dict = config.consumer_configuration_dict

    assert config_dict["enable.auto.commit"] is False
    assert config_dict["group.id"] == "my-group"
    assert config_dict["auto.offset.reset"] == "earliest"
    assert config_dict["client.id"] == "my-client"
    assert config_dict["bootstrap.servers"] == "localhost:9092"
    assert "enable.idempotence" not in config_dict


def test_kafka_config_async_producer_configuration_dict_expect_idempotent_delivery(
    clean_env: None,
) -> None:
    """async_producer_configuration_dict가 aiokafka 키 이름으로 같은 보장을 담는지 검증한다."""
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}GROUP_ID"] = "my-group"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CLIENT_ID"] = "my-client"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS"] = "localhost:9092"

    config = KafkaConnectionConfig()

    assert config.async_producer_configuration_dict == {
        "bootstrap_servers": "localhost:9092",
        "client_id": "my-client",
        "enable_idempotence": True,
        "acks": "all",
    }


def test_kafka_config_async_producer_configuration_dict_with_sasl(
    clean_env: None,
) -> None:
    """async_producer_configuration_dict가 SASL 설정을 aiokafka 키로 전달하는지 검증한다."""
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}GROUP_ID"] = "secure-group"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CLIENT_ID"] = "secure-client"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS"] = "secure:9093"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SECURITY_PROTOCOL"] = "SASL_SSL"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SASL_MECHANISM"] = "PLAIN"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SASL_USERNAME"] = "api-key"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SASL_PASSWORD"] = "api-secret"

    config = KafkaConnectionConfig()

    result = config.async_producer_configuration_dict
    context = result.pop("ssl_context")
    assert isinstance(context, SSLContext)
    assert context.check_hostname
    assert context.verify_mode == CERT_REQUIRED
    assert result == {
        "bootstrap_servers": "secure:9093",
        "client_id": "secure-client",
        "enable_idempotence": True,
        "acks": "all",
        "security_protocol": "SASL_SSL",
        "sasl_mechanism": "PLAIN",
        "sasl_plain_username": "api-key",
        "sasl_plain_password": "api-secret",
    }


def test_kafka_config_connection_configuration_dict_with_sasl(clean_env: None) -> None:
    """SASL 설정이 구성된 경우 connection_configuration_dict에 포함되는지 검증한다."""
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
    config_dict = config.connection_configuration_dict

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
        assert (
            config.consumer_configuration_dict["auto.offset.reset"] == reset_type.value
        )


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


def test_kafka_config_with_custom_dead_letter_settings(clean_env: None) -> None:
    """dead-letter 접미사와 retry 접미사가 환경 변수에서 로드되는지 검증한다."""
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}GROUP_ID"] = "test-group"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CLIENT_ID"] = "test-client"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS"] = "localhost:9092"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}DEAD_LETTER_TOPIC_SUFFIX"] = ".dead"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}RETRY_TOPIC_SUFFIX"] = ".again"

    config = KafkaConnectionConfig()

    assert config.dead_letter_topic_suffix == ".dead"
    assert config.retry_topic_suffix == ".again"


def test_kafka_config_with_retry_policy_environment_expect_nested_policy_loaded(
    clean_env: None,
) -> None:
    """재시도 정책은 중첩 구분자 환경 변수로 필드별 설정된다."""
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}GROUP_ID"] = "test-group"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CLIENT_ID"] = "test-client"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS"] = "localhost:9092"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}RETRY__MAX_ATTEMPTS"] = "5"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}RETRY__INITIAL_INTERVAL"] = "0.5"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}RETRY__MULTIPLIER"] = "3"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}RETRY__MAX_INTERVAL"] = "30"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}RETRY__MODE"] = "delayed"

    config = KafkaConnectionConfig()

    assert config.retry == RetryPolicy(
        max_attempts=5,
        initial_interval=0.5,
        multiplier=3.0,
        max_interval=30.0,
        mode=RetryMode.DELAYED,
    )


def test_kafka_config_with_zero_max_attempts_expect_rejected(
    clean_env: None,
) -> None:
    """첫 전달조차 허용하지 않는 시도 횟수는 설정 로딩에서 거부된다."""
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}GROUP_ID"] = "test-group"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CLIENT_ID"] = "test-client"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS"] = "localhost:9092"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}RETRY__MAX_ATTEMPTS"] = "0"

    with pytest.raises(ValidationError):
        KafkaConnectionConfig()


def test_kafka_config_with_same_retry_and_dead_letter_suffix_expect_rejected(
    clean_env: None,
) -> None:
    """retry와 dead-letter 접미사가 같으면 두 토픽이 겹치므로 거부된다."""
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}GROUP_ID"] = "test-group"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CLIENT_ID"] = "test-client"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS"] = "localhost:9092"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}RETRY_TOPIC_SUFFIX"] = ".dlt"

    with pytest.raises(ValidationError):
        KafkaConnectionConfig()


def test_kafka_config_unnamed_subscriber_expect_base_group_and_topic_names(
    clean_env: None,
) -> None:
    """이름 없는 구독자는 기존 group id와 `<topic>.dlt`를 그대로 쓴다."""
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}GROUP_ID"] = "orders"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CLIENT_ID"] = "test-client"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS"] = "localhost:9092"

    config = KafkaConnectionConfig()

    assert config.subscriber_group_id(None) == "orders"
    assert config.redrive_group_id(None) == "orders.redrive"
    assert config.dead_letter_topic("OrderPlaced", None) == "OrderPlaced.dlt"
    assert config.retry_topic("OrderPlaced", None) == "OrderPlaced.retry"
    assert config.subscriber_consumer_configuration(None) == (
        config.consumer_configuration_dict
    )
    assert config.redrive_consumer_configuration(None) == {
        **config.consumer_configuration_dict,
        "group.id": "orders.redrive",
    }


def test_kafka_config_named_subscriber_expect_own_group_and_topic_names(
    clean_env: None,
) -> None:
    """이름 있는 구독자는 자기 consumer group과 retry·dead-letter 토픽을 가진다."""
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}GROUP_ID"] = "orders"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CLIENT_ID"] = "test-client"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS"] = "localhost:9092"

    config = KafkaConnectionConfig()

    assert config.subscriber_group_id("billing") == "orders.billing"
    assert config.redrive_group_id("billing") == "orders.billing.redrive"
    assert config.dead_letter_topic("OrderPlaced", "billing") == (
        "OrderPlaced.billing.dlt"
    )
    assert config.retry_topic("OrderPlaced", "billing") == "OrderPlaced.billing.retry"
    assert config.subscriber_consumer_configuration("billing")["group.id"] == (
        "orders.billing"
    )
    assert (
        config.subscriber_consumer_configuration("billing")["enable.auto.commit"]
        is False
    )


def test_kafka_config_with_empty_dead_letter_topic_suffix_expect_rejected(
    clean_env: None,
) -> None:
    """빈 접미사는 실패 메시지를 원본 토픽으로 되돌리므로 설정 로딩에서 거부된다."""
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}GROUP_ID"] = "test-group"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CLIENT_ID"] = "test-client"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS"] = "localhost:9092"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}DEAD_LETTER_TOPIC_SUFFIX"] = ""

    with pytest.raises(ValidationError):
        KafkaConnectionConfig()


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


def test_tls_configuration_expect_both_client_backends_use_ca_and_identity(
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """librdkafka와 aiokafka 모두 같은 CA·인증서·키를 사용하며 서버 검증을 유지한다."""
    for key, value in {
        "GROUP_ID": "tls",
        "CLIENT_ID": "tls",
        "BOOTSTRAP_SERVERS": "broker:9093",
        "SECURITY_PROTOCOL": "SSL",
        "SSL_CA_LOCATION": "/tls/ca.crt",
        "SSL_CERTIFICATE_LOCATION": "/tls/user.crt",
        "SSL_KEY_LOCATION": "/tls/user.key",
    }.items():
        monkeypatch.setenv(SPAKKY_KAFKA_CONFIG_ENV_PREFIX + key, value)
    config = KafkaConnectionConfig()
    native = config.connection_configuration_dict
    assert native["ssl.ca.location"] == "/tls/ca.crt"
    assert native["ssl.certificate.location"] == "/tls/user.crt"
    assert native["ssl.key.location"] == "/tls/user.key"
    context = MagicMock(spec=SSLContext)
    with patch(
        "spakky.plugins.kafka.common.config.create_default_context",
        return_value=context,
    ) as create:
        assert config.async_producer_configuration_dict["ssl_context"] is context
    create.assert_called_once_with(cafile="/tls/ca.crt")
    context.load_cert_chain.assert_called_once_with(
        certfile="/tls/user.crt", keyfile="/tls/user.key"
    )


@pytest.mark.parametrize(
    "certificate,key,protocol",
    [("cert", "", "SSL"), ("", "key", "SSL"), ("cert", "key", "PLAINTEXT")],
)
def test_tls_partial_or_plaintext_configuration_expect_rejected(
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
    certificate: str,
    key: str,
    protocol: str,
) -> None:
    """불완전한 client 자격증명과 plaintext로의 잘못된 전환은 설정 단계에서 거부한다."""
    for name, value in {
        "GROUP_ID": "tls",
        "CLIENT_ID": "tls",
        "BOOTSTRAP_SERVERS": "broker:9093",
        "SECURITY_PROTOCOL": protocol,
        "SSL_CERTIFICATE_LOCATION": certificate,
        "SSL_KEY_LOCATION": key,
    }.items():
        monkeypatch.setenv(SPAKKY_KAFKA_CONFIG_ENV_PREFIX + name, value)
    with pytest.raises(ValidationError):
        KafkaConnectionConfig()


def test_tls_invalid_ca_expect_no_plaintext_fallback(
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """잘못된 CA 파일은 SSL context 구성을 실패시키고 암호화를 끄지 않는다."""
    path = tmp_path / "invalid-ca.pem"
    path.write_text("not a certificate")
    for name, value in {
        "GROUP_ID": "tls",
        "CLIENT_ID": "tls",
        "BOOTSTRAP_SERVERS": "broker:9093",
        "SECURITY_PROTOCOL": "SSL",
        "SSL_CA_LOCATION": str(path),
    }.items():
        monkeypatch.setenv(SPAKKY_KAFKA_CONFIG_ENV_PREFIX + name, value)
    config = KafkaConnectionConfig()
    with pytest.raises(SSLError, match="certificate"):
        _ = config.async_producer_configuration_dict


def set_required_environment() -> None:
    """Set the connection settings every configuration test needs."""
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}GROUP_ID"] = "orders"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CLIENT_ID"] = "test-client"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS"] = "localhost:9092"


def test_kafka_config_without_consumer_overrides_expect_unchanged_consumer_settings(
    clean_env: None,
) -> None:
    """override를 주지 않으면 구독자와 redrive consumer 설정이 종전과 같다."""
    set_required_environment()

    config = KafkaConnectionConfig()

    assert config.consumer_overrides == {}
    assert config.subscriber_consumer_overrides == {}
    assert config.subscriber_consumer_configuration("billing") == {
        **config.consumer_configuration_dict,
        "group.id": "orders.billing",
    }
    assert config.redrive_consumer_configuration("billing") == {
        **config.consumer_configuration_dict,
        "group.id": "orders.billing.redrive",
    }


def test_kafka_config_consumer_overrides_from_json_env_expect_applied_to_every_subscriber(
    clean_env: None,
) -> None:
    """CONSUMER_OVERRIDES JSON 환경 변수는 값의 타입을 지켜 모든 구독자의 consumer에 실린다."""
    set_required_environment()
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CONSUMER_OVERRIDES"] = (
        '{"max.poll.interval.ms": 900000, "session.timeout.ms": 45000,'
        ' "check.crcs": true, "partition.assignment.strategy": "cooperative-sticky"}'
    )

    config = KafkaConnectionConfig()

    expected_overrides: dict[str, str | int | float | bool] = {
        "max.poll.interval.ms": 900000,
        "session.timeout.ms": 45000,
        "check.crcs": True,
        "partition.assignment.strategy": "cooperative-sticky",
    }
    assert config.consumer_overrides == expected_overrides
    assert config.consumer_overrides["check.crcs"] is True
    for subscriber in (None, "billing", "shipping"):
        settings = config.subscriber_consumer_configuration(subscriber)
        assert settings.items() >= expected_overrides.items()
        assert settings["group.id"] == config.subscriber_group_id(subscriber)
        assert settings["enable.auto.commit"] is False


def test_kafka_config_subscriber_consumer_overrides_from_json_env_expect_only_that_subscriber(
    clean_env: None,
) -> None:
    """SUBSCRIBER_CONSUMER_OVERRIDES는 이름이 맞는 구독자의 consumer에만 실린다."""
    set_required_environment()
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SUBSCRIBER_CONSUMER_OVERRIDES"] = (
        '{"report-builder": {"max.poll.interval.ms": 900000}}'
    )

    config = KafkaConnectionConfig()

    assert config.subscriber_consumer_overrides == {
        "report-builder": {"max.poll.interval.ms": 900000}
    }
    report_settings = config.subscriber_consumer_configuration("report-builder")
    assert report_settings["max.poll.interval.ms"] == 900000
    assert report_settings["group.id"] == "orders.report-builder"
    assert "max.poll.interval.ms" not in config.subscriber_consumer_configuration(
        "billing"
    )
    assert "max.poll.interval.ms" not in config.subscriber_consumer_configuration(None)


def test_kafka_config_subscriber_override_expect_wins_over_shared_override(
    clean_env: None,
) -> None:
    """같은 키는 구독자 override가 공통 override를 덮고, 다른 키는 둘 다 남는다."""
    set_required_environment()
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CONSUMER_OVERRIDES"] = (
        '{"max.poll.interval.ms": 600000, "fetch.min.bytes": 1024}'
    )
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SUBSCRIBER_CONSUMER_OVERRIDES"] = (
        '{"report-builder": {"max.poll.interval.ms": 900000}}'
    )

    config = KafkaConnectionConfig()

    report_settings = config.subscriber_consumer_configuration("report-builder")
    assert report_settings["max.poll.interval.ms"] == 900000
    assert report_settings["fetch.min.bytes"] == 1024
    billing_settings = config.subscriber_consumer_configuration("billing")
    assert billing_settings["max.poll.interval.ms"] == 600000


def test_kafka_config_override_of_shared_consumer_setting_expect_wins_over_default(
    clean_env: None,
) -> None:
    """override는 공통 consumer 설정 위에 덮이고, producer 설정에는 닿지 않는다."""
    set_required_environment()
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CONSUMER_OVERRIDES"] = (
        '{"client.id": "shared-client"}'
    )
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SUBSCRIBER_CONSUMER_OVERRIDES"] = (
        '{"billing": {"client.id": "billing-client"}}'
    )

    config = KafkaConnectionConfig()

    assert config.subscriber_consumer_configuration(None)["client.id"] == (
        "shared-client"
    )
    assert config.subscriber_consumer_configuration("billing")["client.id"] == (
        "billing-client"
    )
    assert config.producer_configuration_dict["client.id"] == "test-client"


def test_kafka_config_consumer_overrides_expect_applied_to_redrive_consumer(
    clean_env: None,
) -> None:
    """redrive consumer도 공통·구독자 override를 받고 redrive group으로 읽는다."""
    set_required_environment()
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CONSUMER_OVERRIDES"] = (
        '{"fetch.min.bytes": 1024}'
    )
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SUBSCRIBER_CONSUMER_OVERRIDES"] = (
        '{"report-builder": {"max.poll.interval.ms": 900000}}'
    )

    config = KafkaConnectionConfig()

    settings = config.redrive_consumer_configuration("report-builder")
    assert settings["fetch.min.bytes"] == 1024
    assert settings["max.poll.interval.ms"] == 900000
    assert settings["group.id"] == "orders.report-builder.redrive"
    assert settings["enable.auto.commit"] is False


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("group.id", '"other-group"'),
        ("enable.auto.commit", "true"),
        ("auto.offset.reset", '"latest"'),
    ],
)
def test_kafka_config_consumer_overrides_with_reserved_key_expect_rejected(
    clean_env: None, key: str, value: str
) -> None:
    """framework가 정하는 consumer 키를 공통 override로 주면 설정 로딩이 거부한다."""
    set_required_environment()
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CONSUMER_OVERRIDES"] = (
        f'{{"{key}": {value}}}'
    )

    with pytest.raises(ValidationError) as error:
        KafkaConnectionConfig()

    assert error.value.errors()[0]["type"] == "reserved_consumer_override"
    assert error.value.errors()[0]["ctx"] == {"key": key}


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("group.id", '"other-group"'),
        ("enable.auto.commit", "true"),
        ("auto.offset.reset", '"latest"'),
    ],
)
def test_kafka_config_subscriber_consumer_overrides_with_reserved_key_expect_rejected(
    clean_env: None, key: str, value: str
) -> None:
    """framework가 정하는 consumer 키를 구독자 override로 주어도 설정 로딩이 거부한다."""
    set_required_environment()
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SUBSCRIBER_CONSUMER_OVERRIDES"] = (
        f'{{"billing": {{"fetch.min.bytes": 1024, "{key}": {value}}}}}'
    )

    with pytest.raises(ValidationError) as error:
        KafkaConnectionConfig()

    assert error.value.errors()[0]["type"] == "reserved_consumer_override"
    assert error.value.errors()[0]["ctx"] == {"key": key}


def required_environment() -> None:
    """Set the settings every Kafka configuration needs."""
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}GROUP_ID"] = "test-group"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CLIENT_ID"] = "test-client"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS"] = "localhost:9092"


def test_kafka_config_without_subscriber_retry_expect_every_subscriber_uses_retry(
    clean_env: None,
) -> None:
    """선언도 배포 설정도 없으면 모든 subscriber가 config.retry를 쓴다."""
    required_environment()
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}RETRY__MAX_ATTEMPTS"] = "3"

    config = KafkaConnectionConfig()

    assert config.subscriber_retry == {}
    assert config.subscriber_retry_policy(None, None) == config.retry
    assert config.subscriber_retry_policy("billing", None) == config.retry


def test_kafka_config_subscriber_retry_json_expect_only_given_fields_applied(
    clean_env: None,
) -> None:
    """JSON으로 준 subscriber_retry는 적은 필드만 덮고, mode는 코드의 선언을 지킨다."""
    required_environment()
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}RETRY__MAX_INTERVAL"] = "30"
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SUBSCRIBER_RETRY"] = (
        '{"billing-v2": {"max_attempts": 5, "initial_interval": 1.0}}'
    )

    config = KafkaConnectionConfig()

    assert config.subscriber_retry_policy(
        "billing-v2", RetryPolicy(mode=RetryMode.DELAYED, max_attempts=2)
    ) == RetryPolicy(
        max_attempts=5,
        initial_interval=1.0,
        max_interval=30.0,
        mode=RetryMode.DELAYED,
    )


def test_kafka_config_subscriber_retry_expect_other_subscribers_unaffected(
    clean_env: None,
) -> None:
    """한 subscriber의 배포 설정은 다른 subscriber와 이름 없는 subscriber에 닿지 않는다."""
    required_environment()
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SUBSCRIBER_RETRY"] = (
        '{"billing": {"max_attempts": 5}}'
    )

    config = KafkaConnectionConfig()

    assert config.subscriber_retry_policy("shipping", None) == RetryPolicy()
    assert config.subscriber_retry_policy(None, None) == RetryPolicy()


def test_kafka_config_subscriber_retry_empty_key_expect_unnamed_subscriber(
    clean_env: None,
) -> None:
    """빈 문자열 키는 이름 없는 subscriber의 배포 설정이다."""
    required_environment()
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SUBSCRIBER_RETRY"] = (
        '{"": {"mode": "delayed"}}'
    )

    config = KafkaConnectionConfig()

    assert config.subscriber_retry_policy(None, None).mode is RetryMode.DELAYED


@pytest.mark.parametrize("key", ["billing.v2", "dlt", "-billing"])
def test_kafka_config_subscriber_retry_invalid_key_expect_rejected(
    clean_env: None, key: str
) -> None:
    """subscriber 이름이 될 수 없는 키는 설정 로딩에서 거부된다."""
    required_environment()
    environ[f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SUBSCRIBER_RETRY"] = (
        f'{{"{key}": {{"max_attempts": 5}}}}'
    )

    with pytest.raises(ValidationError):
        KafkaConnectionConfig()
