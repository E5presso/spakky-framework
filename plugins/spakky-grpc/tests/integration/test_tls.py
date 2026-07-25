"""Integration tests terminating TLS and mutual TLS on the gRPC listener."""

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from os import environ
from pathlib import Path

import grpc
import grpc.aio
import pytest
import pytest_asyncio
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.plugins.grpc.client import GrpcClient
from spakky.plugins.grpc.config import SPAKKY_GRPC_CONFIG_ENV_PREFIX
from spakky.plugins.grpc.server_spec import GrpcServerSpec

import spakky.plugins.grpc
from tests.integration import apps
from tests.integration.apps.echo import EchoController, EchoRequest

SERVER_HOST = "localhost"
CERTIFICATE_LIFETIME = timedelta(days=1)


@dataclass(frozen=True)
class TlsMaterial:
    """PEM files for a private authority plus the peers it signed."""

    certificate_authority_file: Path
    server_certificate_file: Path
    server_key_file: Path
    client_certificate_file: Path
    client_key_file: Path


@pytest.fixture(name="tls_material", scope="package")
def get_tls_material_fixture(tmp_path_factory: pytest.TempPathFactory) -> TlsMaterial:
    """Issue a throwaway certificate authority and one certificate per peer."""
    directory = tmp_path_factory.mktemp("tls")
    authority_key, authority_certificate = _issue_authority()
    _write(directory / "ca.crt", _certificate_bytes(authority_certificate))

    server_key, server_certificate = _issue_peer(
        SERVER_HOST, authority_key, authority_certificate, with_server_names=True
    )
    _write(directory / "server.crt", _certificate_bytes(server_certificate))
    _write(directory / "server.key", _key_bytes(server_key))

    client_key, client_certificate = _issue_peer(
        "spakky-client", authority_key, authority_certificate, with_server_names=False
    )
    _write(directory / "client.crt", _certificate_bytes(client_certificate))
    _write(directory / "client.key", _key_bytes(client_key))

    return TlsMaterial(
        certificate_authority_file=directory / "ca.crt",
        server_certificate_file=directory / "server.crt",
        server_key_file=directory / "server.key",
        client_certificate_file=directory / "client.crt",
        client_key_file=directory / "client.key",
    )


@pytest.fixture(name="tls_app")
def get_tls_app_fixture(tls_material: TlsMaterial) -> Iterator[SpakkyApplication]:
    """Boot an application whose listener terminates server-side TLS."""
    yield from _booted_app(
        {
            "BIND_ADDRESSES": f'["{SERVER_HOST}:0"]',
            "TLS_CERTIFICATE_CHAIN_FILE": str(tls_material.server_certificate_file),
            "TLS_PRIVATE_KEY_FILE": str(tls_material.server_key_file),
        }
    )


@pytest.fixture(name="mutual_tls_app")
def get_mutual_tls_app_fixture(
    tls_material: TlsMaterial,
) -> Iterator[SpakkyApplication]:
    """Boot an application that also demands a client certificate."""
    yield from _booted_app(
        {
            "BIND_ADDRESSES": f'["{SERVER_HOST}:0"]',
            "TLS_CERTIFICATE_CHAIN_FILE": str(tls_material.server_certificate_file),
            "TLS_PRIVATE_KEY_FILE": str(tls_material.server_key_file),
            "TLS_CLIENT_CA_FILE": str(tls_material.certificate_authority_file),
            "REQUIRE_CLIENT_AUTH": "true",
        }
    )


@pytest_asyncio.fixture(name="tls_channel")
async def get_tls_channel_fixture(
    tls_app: SpakkyApplication, tls_material: TlsMaterial
) -> AsyncIterator[grpc.aio.Channel]:
    """Open a TLS channel trusting the throwaway authority."""
    channel = grpc.aio.secure_channel(
        f"{SERVER_HOST}:{_port_of(tls_app)}",
        grpc.ssl_channel_credentials(
            root_certificates=tls_material.certificate_authority_file.read_bytes()
        ),
    )
    try:
        yield channel
    finally:
        await channel.close()


@pytest.mark.asyncio
async def test_unary_call_over_tls_expect_reply(tls_channel: grpc.aio.Channel) -> None:
    """A TLS listener must serve ordinary code-first calls unchanged."""
    client = GrpcClient(tls_channel, EchoController)

    reply = await client.unary_unary(EchoController.unary_echo)(
        EchoRequest(text="secure")
    )

    assert reply.text == "secure"


@pytest.mark.asyncio
async def test_plaintext_call_against_tls_listener_expect_failure(
    tls_app: SpakkyApplication,
) -> None:
    """A plaintext client must not be able to reach a TLS listener."""
    channel = grpc.aio.insecure_channel(f"{SERVER_HOST}:{_port_of(tls_app)}")
    try:
        client = GrpcClient(channel, EchoController)
        with pytest.raises(grpc.aio.AioRpcError):
            await client.unary_unary(EchoController.unary_echo)(
                EchoRequest(text="cleartext"), timeout=5
            )
    finally:
        await channel.close()


@pytest.mark.asyncio
async def test_mutual_tls_call_with_client_certificate_expect_reply(
    mutual_tls_app: SpakkyApplication, tls_material: TlsMaterial
) -> None:
    """A client presenting a certificate signed by the trusted CA is served."""
    channel = grpc.aio.secure_channel(
        f"{SERVER_HOST}:{_port_of(mutual_tls_app)}",
        grpc.ssl_channel_credentials(
            root_certificates=tls_material.certificate_authority_file.read_bytes(),
            private_key=tls_material.client_key_file.read_bytes(),
            certificate_chain=tls_material.client_certificate_file.read_bytes(),
        ),
    )
    try:
        client = GrpcClient(channel, EchoController)
        reply = await client.unary_unary(EchoController.unary_echo)(
            EchoRequest(text="mutual")
        )
        assert reply.text == "mutual"
    finally:
        await channel.close()


@pytest.mark.asyncio
async def test_mutual_tls_call_without_client_certificate_expect_failure(
    mutual_tls_app: SpakkyApplication, tls_material: TlsMaterial
) -> None:
    """A client without a certificate is rejected when client auth is required."""
    channel = grpc.aio.secure_channel(
        f"{SERVER_HOST}:{_port_of(mutual_tls_app)}",
        grpc.ssl_channel_credentials(
            root_certificates=tls_material.certificate_authority_file.read_bytes()
        ),
    )
    try:
        client = GrpcClient(channel, EchoController)
        with pytest.raises(grpc.aio.AioRpcError):
            await client.unary_unary(EchoController.unary_echo)(
                EchoRequest(text="anonymous"), timeout=5
            )
    finally:
        await channel.close()


def _booted_app(settings: dict[str, str]) -> Iterator[SpakkyApplication]:
    """Boot an application with *settings* exported as plugin environment."""
    previous = {
        name: environ.get(f"{SPAKKY_GRPC_CONFIG_ENV_PREFIX}{name}") for name in settings
    }
    for name, value in settings.items():
        environ[f"{SPAKKY_GRPC_CONFIG_ENV_PREFIX}{name}"] = value
    try:
        app = (
            SpakkyApplication(ApplicationContext())
            .load_plugins(include={spakky.plugins.grpc.PLUGIN_NAME})
            .scan(apps)
        )
        app.start()
    finally:
        for name, value in previous.items():
            variable = f"{SPAKKY_GRPC_CONFIG_ENV_PREFIX}{name}"
            if value is None:
                environ.pop(variable, None)
            else:
                environ[variable] = value
    try:
        yield app
    finally:
        app.stop()


def _port_of(app: SpakkyApplication) -> int:
    """Return the OS-assigned port the TLS server is listening on."""
    return app.container.get(GrpcServerSpec).bound_ports[0]


def _issue_authority() -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    """Create a self-signed certificate authority for the test run."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "spakky-test-ca")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - CERTIFICATE_LIFETIME)
        .not_valid_after(now + CERTIFICATE_LIFETIME)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    return key, certificate


def _issue_peer(
    common_name: str,
    authority_key: rsa.RSAPrivateKey,
    authority_certificate: x509.Certificate,
    with_server_names: bool,
) -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    """Issue a certificate for one peer, signed by the test authority."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(UTC)
    builder = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)]))
        .issuer_name(authority_certificate.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - CERTIFICATE_LIFETIME)
        .not_valid_after(now + CERTIFICATE_LIFETIME)
    )
    if with_server_names:
        builder = builder.add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName(SERVER_HOST),
                    x509.IPAddress(ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
    return key, builder.sign(authority_key, hashes.SHA256())


def _certificate_bytes(certificate: x509.Certificate) -> bytes:
    """Serialise a certificate to PEM."""
    return certificate.public_bytes(serialization.Encoding.PEM)


def _key_bytes(key: rsa.RSAPrivateKey) -> bytes:
    """Serialise a private key to unencrypted PEM."""
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _write(path: Path, content: bytes) -> None:
    """Write PEM *content* to *path*."""
    path.write_bytes(content)
