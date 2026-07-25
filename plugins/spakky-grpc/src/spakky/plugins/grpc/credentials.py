"""Transport security credentials for the gRPC listener.

Translates the PEM file paths declared in :class:`GrpcConfig` into a
``grpc.ServerCredentials`` object. A half-configured key pair is rejected
up front rather than silently degrading to a plaintext listener, because a
deployment that asked for TLS must never end up serving cleartext.
"""

import grpc

from spakky.plugins.grpc.config import GrpcConfig
from spakky.plugins.grpc.error import (
    IncompleteTlsCredentialsError,
    MissingClientCertificateAuthorityError,
)


def build_server_credentials(config: GrpcConfig) -> grpc.ServerCredentials | None:
    """Build listener credentials from the configured PEM files.

    Args:
        config: Plugin configuration carrying the TLS file paths.

    Returns:
        Credentials for a TLS listener, or ``None`` when no transport
        security setting is present and the listener stays plaintext.

    Raises:
        IncompleteTlsCredentialsError: If some transport security setting is
            present but the certificate chain or private key is missing.
        MissingClientCertificateAuthorityError: If client certificate
            authentication is required without a client CA file.
    """
    if not _has_transport_security_setting(config):
        return None
    if config.tls_certificate_chain_file is None or config.tls_private_key_file is None:
        raise IncompleteTlsCredentialsError(
            config.tls_certificate_chain_file,
            config.tls_private_key_file,
        )
    if config.require_client_auth and config.tls_client_ca_file is None:
        raise MissingClientCertificateAuthorityError

    return grpc.ssl_server_credentials(
        [
            (
                config.tls_private_key_file.read_bytes(),
                config.tls_certificate_chain_file.read_bytes(),
            )
        ],
        root_certificates=(
            config.tls_client_ca_file.read_bytes()
            if config.tls_client_ca_file is not None
            else None
        ),
        require_client_auth=config.require_client_auth,
    )


def _has_transport_security_setting(config: GrpcConfig) -> bool:
    """Return whether any transport security setting was configured."""
    return (
        config.tls_certificate_chain_file is not None
        or config.tls_private_key_file is not None
        or config.tls_client_ca_file is not None
        or config.require_client_auth
    )
