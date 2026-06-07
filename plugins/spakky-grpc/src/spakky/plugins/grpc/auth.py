"""gRPC auth boundary helpers."""

from collections.abc import Sequence

import grpc
import grpc.aio
from spakky.auth import (
    AUTH_CONTEXT_SNAPSHOT_HEADER_KEY,
    AUTH_CONTEXT_SNAPSHOT_METADATA_KEY,
    AuthInvocation,
    CredentialCarrier,
    CredentialCarrierKind,
    CredentialCarrierLocation,
    IAuthenticationProvider,
    store_auth_context,
)
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.container import IContainer

from spakky.plugins.grpc.error import Unavailable

AUTHORIZATION_METADATA_KEY = "authorization"
BEARER_SCHEME = "bearer"
GRPC_AUTH_BOUNDARY = "grpc"


def seed_grpc_auth_context(
    *,
    container: IContainer,
    application_context: IApplicationContext,
    context: grpc.aio.ServicerContext,
    operation: str,
) -> None:
    """Authenticate gRPC metadata and seed AuthContext when credentials exist."""
    credential = _extract_credential(context.invocation_metadata())
    if credential is None:
        return
    provider = container.get_or_none(IAuthenticationProvider)
    if provider is None:
        raise Unavailable()
    auth_context = provider.authenticate(
        credential,
        AuthInvocation(boundary=GRPC_AUTH_BOUNDARY, operation=operation),
    )
    store_auth_context(application_context, auth_context)


def _extract_credential(
    metadata: grpc.aio.Metadata | Sequence[tuple[str, str | bytes]] | None,
) -> CredentialCarrier | None:
    if metadata is None:
        return None
    authorization = _metadata_value(metadata, AUTHORIZATION_METADATA_KEY)
    if authorization is not None:
        return _authorization_credential(authorization)
    snapshot = _metadata_value(metadata, AUTH_CONTEXT_SNAPSHOT_METADATA_KEY)
    if snapshot is None:
        snapshot = _metadata_value(metadata, AUTH_CONTEXT_SNAPSHOT_HEADER_KEY)
    if snapshot is None:
        return None
    return CredentialCarrier(
        kind=CredentialCarrierKind.AUTH_CONTEXT_SNAPSHOT,
        location=CredentialCarrierLocation.METADATA,
        material=snapshot,
        name=AUTH_CONTEXT_SNAPSHOT_METADATA_KEY,
    )


def _metadata_value(
    metadata: grpc.aio.Metadata | Sequence[tuple[str, str | bytes]],
    name: str,
) -> str | None:
    if isinstance(metadata, grpc.aio.Metadata):
        value = metadata.get(name)
        return _text_value(value)
    for key, value in metadata:
        if key.lower() == name:
            return _text_value(value)
    return None


def _authorization_credential(value: str) -> CredentialCarrier | None:
    scheme, separator, material = value.partition(" ")
    if separator == "" or scheme.lower() != BEARER_SCHEME or material == "":
        return None
    return CredentialCarrier(
        kind=CredentialCarrierKind.BEARER_TOKEN,
        location=CredentialCarrierLocation.METADATA,
        material=material,
        name=AUTHORIZATION_METADATA_KEY,
        scheme="Bearer",
    )


def _text_value(value: str | bytes | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode()
    return value
