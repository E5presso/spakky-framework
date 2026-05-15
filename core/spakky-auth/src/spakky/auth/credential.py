"""Provider-neutral credential carrier model."""

from dataclasses import dataclass
from enum import StrEnum


class CredentialCarrierKind(StrEnum):
    """Canonical credential material categories accepted by auth providers."""

    BEARER_TOKEN = "BEARER_TOKEN"
    API_KEY = "API_KEY"
    BASIC = "BASIC"
    CLIENT_CERTIFICATE = "CLIENT_CERTIFICATE"
    AUTH_CONTEXT_SNAPSHOT = "AUTH_CONTEXT_SNAPSHOT"


class CredentialCarrierLocation(StrEnum):
    """Where an inbound adapter observed credential material."""

    AUTHORIZATION_HEADER = "AUTHORIZATION_HEADER"
    HEADER = "HEADER"
    METADATA = "METADATA"
    COOKIE = "COOKIE"
    CLI_OPTION = "CLI_OPTION"
    APPLICATION_CONTEXT = "APPLICATION_CONTEXT"


@dataclass(frozen=True, slots=True, kw_only=True)
class CredentialCarrier:
    """Boundary-local credential material handed to an auth provider."""

    kind: CredentialCarrierKind
    """Provider-neutral credential category."""

    location: CredentialCarrierLocation
    """Transport location where the credential was discovered."""

    material: str
    """Opaque credential material read by the inbound adapter."""

    name: str | None = None
    """Optional transport field name, such as an HTTP header name."""

    scheme: str | None = None
    """Optional credential scheme, such as Bearer."""
