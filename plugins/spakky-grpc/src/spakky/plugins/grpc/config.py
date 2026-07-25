"""gRPC plugin configuration."""

from pathlib import Path
from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict
from spakky.core.stereotype.configuration import Configuration

SPAKKY_GRPC_CONFIG_ENV_PREFIX = "SPAKKY_GRPC_"
"""Environment prefix for gRPC plugin settings."""

type GrpcServerOptions = dict[str, int | str]
"""gRPC channel arguments keyed by their documented ``grpc.*`` option name."""


@Configuration()
class GrpcConfig(BaseSettings):
    """Configuration for the gRPC server integration."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix=SPAKKY_GRPC_CONFIG_ENV_PREFIX,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
    )

    bind_addresses: tuple[str, ...] = ()
    """Addresses the server listens on, each in ``host:port`` form."""

    server_options: GrpcServerOptions = {}
    """Channel arguments forwarded verbatim to ``grpc.aio.server(options=...)``.

    Any documented gRPC channel argument is accepted, so keepalive intervals
    (``grpc.keepalive_time_ms``), message size caps
    (``grpc.max_receive_message_length``) and connection lifetime limits
    (``grpc.max_connection_age_ms``) are all tunable without this plugin
    enumerating them one by one.
    """

    tls_certificate_chain_file: Path | None = None
    """PEM file with the server certificate chain. ``None`` means TLS is off."""

    tls_private_key_file: Path | None = None
    """PEM file with the private key matching the certificate chain."""

    tls_client_ca_file: Path | None = None
    """PEM file of authorities trusted to sign client certificates (mutual TLS)."""

    require_client_auth: bool = False
    """Whether clients must present a certificate signed by ``tls_client_ca_file``."""

    health_service_enabled: bool = True
    """Whether to expose the standard ``grpc.health.v1.Health`` service."""

    reflection_service_enabled: bool = True
    """Whether to expose the standard server reflection service."""

    def __init__(self) -> None:
        super().__init__()
