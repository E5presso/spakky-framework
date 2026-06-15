"""gRPC plugin configuration."""

from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict
from spakky.core.stereotype.configuration import Configuration

SPAKKY_GRPC_CONFIG_ENV_PREFIX = "SPAKKY_GRPC_"
"""Environment prefix for gRPC plugin settings."""


@Configuration()
class GrpcConfig(BaseSettings):
    """Configuration for the gRPC server integration."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix=SPAKKY_GRPC_CONFIG_ENV_PREFIX,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )

    bind_addresses: tuple[str, ...] = ()
    """Address list passed to GrpcServerSpec.add_insecure_port()."""

    def __init__(self) -> None:
        super().__init__()
