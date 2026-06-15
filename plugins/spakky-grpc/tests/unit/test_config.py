"""Tests for gRPC plugin configuration."""

import pytest

from spakky.plugins.grpc.config import (
    SPAKKY_GRPC_CONFIG_ENV_PREFIX,
    GrpcConfig,
)


def test_grpc_config_loads_bind_addresses_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GrpcConfig reads bind address list from SPAKKY_GRPC_* env."""
    monkeypatch.setenv(
        f"{SPAKKY_GRPC_CONFIG_ENV_PREFIX}BIND_ADDRESSES",
        '["127.0.0.1:50051", "127.0.0.1:50052"]',
    )

    config = GrpcConfig()

    assert config.bind_addresses == ("127.0.0.1:50051", "127.0.0.1:50052")
