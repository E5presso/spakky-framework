"""Unit tests for gRPC auth boundary helpers."""

import grpc.aio
from spakky.auth import (
    AUTH_CONTEXT_SNAPSHOT_HEADER_KEY,
    AUTH_CONTEXT_SNAPSHOT_METADATA_KEY,
    CredentialCarrierKind,
)

from spakky.plugins.grpc.auth import _extract_credential, _text_value


def test_extract_credential_returns_none_for_missing_metadata() -> None:
    """Missing invocation metadata should not seed an auth credential."""
    assert _extract_credential(None) is None


def test_extract_credential_returns_none_for_missing_supported_keys() -> None:
    """Metadata without supported auth keys should be ignored."""
    assert _extract_credential((("x-custom", "value"),)) is None


def test_extract_credential_returns_none_for_unsupported_authorization_scheme() -> None:
    """Only Bearer authorization metadata should become a credential."""
    assert _extract_credential((("authorization", "Basic abc"),)) is None


def test_extract_credential_reads_bearer_metadata_object() -> None:
    """grpc.aio.Metadata values should be read as auth credentials."""
    metadata = grpc.aio.Metadata(("authorization", "Bearer metadata-token"))

    credential = _extract_credential(metadata)

    assert credential is not None
    assert credential.kind is CredentialCarrierKind.BEARER_TOKEN
    assert credential.material == "metadata-token"


def test_extract_credential_reads_snapshot_metadata_key() -> None:
    """Snapshot propagation metadata should become a snapshot credential."""
    credential = _extract_credential(
        ((AUTH_CONTEXT_SNAPSHOT_METADATA_KEY, "snapshot-envelope"),)
    )

    assert credential is not None
    assert credential.kind is CredentialCarrierKind.AUTH_CONTEXT_SNAPSHOT
    assert credential.material == "snapshot-envelope"


def test_extract_credential_reads_snapshot_header_fallback() -> None:
    """Snapshot propagation should accept the header-style metadata key."""
    credential = _extract_credential(
        ((AUTH_CONTEXT_SNAPSHOT_HEADER_KEY, "header-envelope"),)
    )

    assert credential is not None
    assert credential.kind is CredentialCarrierKind.AUTH_CONTEXT_SNAPSHOT
    assert credential.material == "header-envelope"


def test_text_value_returns_none_for_missing_value() -> None:
    """Missing metadata values should remain absent."""
    assert _text_value(None) is None


def test_text_value_decodes_binary_metadata_value() -> None:
    """Binary metadata values should be decoded to text."""
    assert _text_value(b"binary-token") == "binary-token"
