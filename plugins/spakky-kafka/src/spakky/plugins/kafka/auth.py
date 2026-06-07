"""Authentication helpers for Kafka consumer boundaries."""

from dataclasses import dataclass

from spakky.auth import (
    AUTH_CONTEXT_SNAPSHOT_HEADER_KEY,
    AUTH_CONTEXT_SNAPSHOT_METADATA_KEY,
    EXPIRED_SNAPSHOT_DECISION,
    INVALID_SNAPSHOT_DECISION,
    MISSING_SNAPSHOT_DECISION,
    AuthInvocation,
    AuthInvocationAttribute,
    AuthVerificationProviderUnavailableError,
    AuthorizationDecision,
    ExpiredAuthContextSnapshotError,
    IAuthContextSnapshotVerifier,
    InvalidAuthContextSnapshotError,
    MissingAuthContextSnapshotError,
    store_auth_context,
)
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.container import IContainer

KAFKA_AUTH_BOUNDARY = "kafka"
"""Provider-neutral boundary name used for Kafka AuthInvocation values."""

KAFKA_AUTH_HEADERS_PARAMETER = "_spakky_kafka_headers"
"""Internal endpoint keyword used to pass Kafka message headers."""


@dataclass(frozen=True, slots=True, kw_only=True)
class KafkaHandlerAuthBinding:
    """Auth metadata captured for one registered Kafka event handler."""

    operation: str
    """Canonical handler operation reference."""
    protected: bool
    """Whether the handler has effective protected auth metadata."""


class KafkaAuthBoundary:
    """Verify propagated snapshots and seed AuthContext for Kafka handlers."""

    _container: IContainer
    _application_context: IApplicationContext

    def __init__(
        self,
        container: IContainer,
        application_context: IApplicationContext,
    ) -> None:
        self._container = container
        self._application_context = application_context

    def seed_auth_context(
        self,
        headers: dict[str, str],
        binding: KafkaHandlerAuthBinding,
    ) -> AuthorizationDecision:
        """Verify a Kafka snapshot header and store AuthContext before user code."""
        snapshot = self._snapshot_header(headers)
        if snapshot is None:
            if binding.protected:
                return MISSING_SNAPSHOT_DECISION
            return AuthorizationDecision.allow()
        verifier = self._container.get_or_none(IAuthContextSnapshotVerifier)
        if verifier is None:
            raise AuthVerificationProviderUnavailableError()
        try:
            auth_context = verifier.verify_snapshot(
                snapshot,
                self._invocation(binding),
            )
        except MissingAuthContextSnapshotError:
            return MISSING_SNAPSHOT_DECISION
        except InvalidAuthContextSnapshotError:
            return INVALID_SNAPSHOT_DECISION
        except ExpiredAuthContextSnapshotError:
            return EXPIRED_SNAPSHOT_DECISION
        except AuthVerificationProviderUnavailableError:
            raise
        store_auth_context(self._application_context, auth_context)
        return AuthorizationDecision.allow()

    def _snapshot_header(self, headers: dict[str, str]) -> str | None:
        for name in (
            AUTH_CONTEXT_SNAPSHOT_HEADER_KEY,
            AUTH_CONTEXT_SNAPSHOT_METADATA_KEY,
        ):
            value = self._header_value(headers, name)
            if value is not None and value != "":
                return value
        return None

    def _header_value(self, headers: dict[str, str], name: str) -> str | None:
        value = headers.get(name)
        if value is not None:
            return value
        lower_name = name.lower()
        for key, candidate in headers.items():
            if key.lower() == lower_name:
                return candidate
        return None

    def _invocation(self, binding: KafkaHandlerAuthBinding) -> AuthInvocation:
        return AuthInvocation(
            boundary=KAFKA_AUTH_BOUNDARY,
            operation=binding.operation,
            attributes=(
                AuthInvocationAttribute(name="handler", value=binding.operation),
            ),
        )
