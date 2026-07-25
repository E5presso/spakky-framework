"""Unit tests for translating TLS configuration into listener credentials."""

from pathlib import Path

import grpc
import pytest
from spakky.plugins.grpc.config import GrpcConfig
from spakky.plugins.grpc.credentials import build_server_credentials
from spakky.plugins.grpc.error import (
    IncompleteTlsCredentialsError,
    MissingClientCertificateAuthorityError,
)


def _config(
    tls_certificate_chain_file: Path | None = None,
    tls_private_key_file: Path | None = None,
    tls_client_ca_file: Path | None = None,
    require_client_auth: bool = False,
) -> GrpcConfig:
    """Build a GrpcConfig carrying only the transport security fields."""
    return GrpcConfig.model_construct(
        bind_addresses=(),
        server_options={},
        tls_certificate_chain_file=tls_certificate_chain_file,
        tls_private_key_file=tls_private_key_file,
        tls_client_ca_file=tls_client_ca_file,
        require_client_auth=require_client_auth,
        health_service_enabled=True,
        reflection_service_enabled=True,
    )


def test_build_server_credentials_without_any_tls_setting_expect_none() -> None:
    """A configuration with no transport security stays a plaintext listener."""
    assert build_server_credentials(_config()) is None


def test_build_server_credentials_with_key_pair_expect_credentials(
    tls_key_pair: tuple[Path, Path],
) -> None:
    """A complete certificate chain and private key produce TLS credentials."""
    certificate_chain_file, private_key_file = tls_key_pair

    credentials = build_server_credentials(
        _config(
            tls_certificate_chain_file=certificate_chain_file,
            tls_private_key_file=private_key_file,
        )
    )

    assert isinstance(credentials, grpc.ServerCredentials)


def test_build_server_credentials_without_private_key_expect_error(
    tls_key_pair: tuple[Path, Path],
) -> None:
    """A certificate without its private key must fail instead of serving plaintext."""
    certificate_chain_file, _ = tls_key_pair

    with pytest.raises(IncompleteTlsCredentialsError):
        build_server_credentials(
            _config(tls_certificate_chain_file=certificate_chain_file)
        )


def test_build_server_credentials_without_certificate_chain_expect_error(
    tls_key_pair: tuple[Path, Path],
) -> None:
    """A private key without its certificate chain must fail the same way."""
    _, private_key_file = tls_key_pair

    with pytest.raises(IncompleteTlsCredentialsError):
        build_server_credentials(_config(tls_private_key_file=private_key_file))


def test_build_server_credentials_with_client_ca_only_expect_error(
    tls_key_pair: tuple[Path, Path],
) -> None:
    """A client CA without server key material is an incomplete TLS setup."""
    certificate_chain_file, _ = tls_key_pair

    with pytest.raises(IncompleteTlsCredentialsError):
        build_server_credentials(_config(tls_client_ca_file=certificate_chain_file))


def test_build_server_credentials_requiring_client_auth_without_ca_expect_error(
    tls_key_pair: tuple[Path, Path],
) -> None:
    """Client certificate authentication needs an authority to verify against."""
    certificate_chain_file, private_key_file = tls_key_pair

    with pytest.raises(MissingClientCertificateAuthorityError):
        build_server_credentials(
            _config(
                tls_certificate_chain_file=certificate_chain_file,
                tls_private_key_file=private_key_file,
                require_client_auth=True,
            )
        )


def test_build_server_credentials_with_client_ca_expect_credentials(
    tls_key_pair: tuple[Path, Path],
) -> None:
    """Mutual TLS with a client CA produces credentials rather than failing."""
    certificate_chain_file, private_key_file = tls_key_pair

    credentials = build_server_credentials(
        _config(
            tls_certificate_chain_file=certificate_chain_file,
            tls_private_key_file=private_key_file,
            tls_client_ca_file=certificate_chain_file,
            require_client_auth=True,
        )
    )

    assert isinstance(credentials, grpc.ServerCredentials)
