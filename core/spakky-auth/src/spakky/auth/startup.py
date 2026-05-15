"""Feature-local startup validation for auth capability contributions."""

from dataclasses import dataclass
from inspect import getmembers_static
import threading
from typing import override

from spakky.auth.capability import AuthCapability
from spakky.auth.contribution import (
    AuthContributionProviderId,
    AuthProviderContribution,
)
from spakky.auth.error import AbstractSpakkyAuthError
from spakky.auth.metadata import (
    AuthRequirementKind,
    EffectiveAuthMetadata,
    get_effective_auth_metadata,
    has_auth_boundary_metadata,
)
from spakky.core.application.startup_diagnostics import (
    IStartupDiagnosticDetailProvider,
    StartupDiagnosticDetail,
    StartupDiagnosticDetails,
)
from spakky.core.pod.annotations.order import Order
from spakky.core.pod.annotations.pod import Pod, PodType
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.container import IContainer
from spakky.core.service.interfaces.service import IService

AUTH_STARTUP_VALIDATION_ERROR_DETAIL_KEY = "auth.capability.validation.error"
"""Startup diagnostic detail key for invalid auth capability provider counts."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthSnapshotPropagationConfig:
    """Feature-local config declaring signed AuthContextSnapshot propagation use."""

    enabled: bool = False
    """Whether this application propagates signed AuthContextSnapshot envelopes."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthStartupCapabilityDiagnostic:
    """Structured diagnostic for one invalid required auth capability count."""

    capability: AuthCapability
    """Capability required by protected metadata or snapshot propagation."""

    provider_count: int
    """Number of auth provider contributions declaring the capability."""

    provider_ids: tuple[AuthContributionProviderId, ...]
    """Provider identifiers declaring the capability."""

    required_by: tuple[str, ...]
    """Startup configuration or scanned boundary sources requiring the capability."""

    def as_startup_diagnostic_detail(self) -> StartupDiagnosticDetail:
        """Convert this auth diagnostic into a startup report detail."""
        return StartupDiagnosticDetail(
            key=AUTH_STARTUP_VALIDATION_ERROR_DETAIL_KEY,
            value=(
                f"capability={self.capability.value};"
                f"provider_count={self.provider_count};"
                f"providers={','.join(self.provider_ids)};"
                f"required_by={','.join(self.required_by)}"
            ),
        )


class AuthStartupCapabilityValidationError(
    AbstractSpakkyAuthError,
    IStartupDiagnosticDetailProvider,
):
    """Raised when required auth capabilities have zero or multiple providers."""

    message = "Auth startup capability validation failed"

    diagnostics: tuple[AuthStartupCapabilityDiagnostic, ...]

    def __init__(
        self,
        diagnostics: tuple[AuthStartupCapabilityDiagnostic, ...],
    ) -> None:
        self.diagnostics = diagnostics
        super().__init__(self.message)

    @property
    @override
    def startup_diagnostic_details(self) -> StartupDiagnosticDetails:
        """Return diagnostics attachable to the startup failure summary."""
        return tuple(
            diagnostic.as_startup_diagnostic_detail() for diagnostic in self.diagnostics
        )


class AuthStartupContainerUnavailableError(AbstractSpakkyAuthError):
    """Raised when startup validation runs before container injection."""

    message = "Auth startup validation container is unavailable"


class AuthCapabilityStartupValidator:
    """Validate auth capability providers required by this application."""

    _container: IContainer

    def __init__(self, container: IContainer) -> None:
        self._container = container

    def validate(self) -> None:
        """Validate required capability provider counts and fail fast on mismatch."""
        diagnostics = self._invalid_capability_diagnostics()
        if len(diagnostics) > 0:
            raise AuthStartupCapabilityValidationError(diagnostics=diagnostics)

    def _invalid_capability_diagnostics(
        self,
    ) -> tuple[AuthStartupCapabilityDiagnostic, ...]:
        required_capabilities = self._required_capabilities()
        contributions = self._auth_provider_contributions()
        diagnostics: list[AuthStartupCapabilityDiagnostic] = []
        for capability in sorted(
            required_capabilities,
            key=lambda item: item.value,
        ):
            provider_ids = tuple(
                sorted(
                    contribution.provider_id
                    for contribution in contributions
                    if contribution.supports(capability)
                )
            )
            provider_count = len(provider_ids)
            if provider_count != 1:
                diagnostics.append(
                    AuthStartupCapabilityDiagnostic(
                        capability=capability,
                        provider_count=provider_count,
                        provider_ids=provider_ids,
                        required_by=tuple(sorted(required_capabilities[capability])),
                    )
                )
        return tuple(diagnostics)

    def _required_capabilities(self) -> dict[AuthCapability, set[str]]:
        required: dict[AuthCapability, set[str]] = {}
        for pod in self._container.pods.values():
            for metadata, source in self._protected_metadata_sources(pod.target):
                if metadata.protected:
                    self._record_required_capability(
                        required,
                        AuthCapability.AUTHENTICATION,
                        source,
                    )
                    self._record_protected_requirement_capabilities(
                        required,
                        metadata,
                        source,
                    )
        for source in self._enabled_snapshot_propagation_sources():
            self._record_required_capability(
                required,
                AuthCapability.SNAPSHOT_SIGN,
                source,
            )
            self._record_required_capability(
                required,
                AuthCapability.SNAPSHOT_VERIFY,
                source,
            )
        return required

    def _protected_metadata_sources(
        self,
        target: PodType,
    ) -> tuple[tuple[EffectiveAuthMetadata, str], ...]:
        sources: list[tuple[EffectiveAuthMetadata, str]] = []
        if has_auth_boundary_metadata(target):
            sources.append(
                (get_effective_auth_metadata(target), self._source_name(target))
            )
        if isinstance(target, type):
            for name, member in getmembers_static(target):
                if callable(member) and has_auth_boundary_metadata(member):
                    sources.append(
                        (
                            get_effective_auth_metadata(member, owner_type=target),
                            f"{self._source_name(target)}.{name}",
                        )
                    )
        return tuple(sources)

    def _source_name(self, target: PodType) -> str:
        return f"{target.__module__}.{target.__qualname__}"

    def _record_protected_requirement_capabilities(
        self,
        required: dict[AuthCapability, set[str]],
        metadata: EffectiveAuthMetadata,
        source: str,
    ) -> None:
        for requirement in metadata.requirements:
            if requirement.kind is AuthRequirementKind.PERMISSION:
                self._record_required_capability(
                    required,
                    AuthCapability.PERMISSION_CHECK,
                    source,
                )
            if requirement.kind is AuthRequirementKind.POLICY:
                self._record_required_capability(
                    required,
                    AuthCapability.POLICY_EVALUATION,
                    source,
                )
            if requirement.kind is AuthRequirementKind.RELATION:
                self._record_required_capability(
                    required,
                    AuthCapability.RELATION_CHECK,
                    source,
                )
            if requirement.kind is AuthRequirementKind.ROLE:
                self._record_required_capability(
                    required,
                    AuthCapability.ROLE_CHECK,
                    source,
                )
            if requirement.kind is AuthRequirementKind.SCOPE:
                self._record_required_capability(
                    required,
                    AuthCapability.SCOPE_CHECK,
                    source,
                )

    def _record_required_capability(
        self,
        required: dict[AuthCapability, set[str]],
        capability: AuthCapability,
        source: str,
    ) -> None:
        if capability not in required:
            required[capability] = set()
        required[capability].add(source)

    def _enabled_snapshot_propagation_sources(self) -> tuple[str, ...]:
        sources: list[str] = []
        for config in self._snapshot_propagation_configs():
            if config.enabled:
                sources.append("AuthSnapshotPropagationConfig.enabled")
        return tuple(sources)

    def _snapshot_propagation_configs(
        self,
    ) -> tuple[AuthSnapshotPropagationConfig, ...]:
        return tuple(
            config
            for config in self._container.find(
                lambda pod: pod.type_ is AuthSnapshotPropagationConfig
            )
            if isinstance(config, AuthSnapshotPropagationConfig)
        )

    def _auth_provider_contributions(self) -> tuple[AuthProviderContribution, ...]:
        return tuple(
            contribution
            for contribution in self._container.find(
                lambda pod: pod.type_ is AuthProviderContribution
            )
            if isinstance(contribution, AuthProviderContribution)
        )


@Order(0)
@Pod()
class AuthCapabilityStartupValidationService(IService, IContainerAware):
    """Service that runs auth capability validation before user services start."""

    _validator: AuthCapabilityStartupValidator | None
    _stop_event: threading.Event | None

    def __init__(self) -> None:
        self._validator = None
        self._stop_event = None

    @override
    def set_container(self, container: IContainer) -> None:
        """Inject the application container for startup validation."""
        self._validator = AuthCapabilityStartupValidator(container=container)

    @override
    def set_stop_event(self, stop_event: threading.Event) -> None:
        """Store the lifecycle stop event supplied by the application context."""
        self._stop_event = stop_event

    @override
    def start(self) -> None:
        """Validate auth capabilities before subsequent services start."""
        if self._validator is None:
            raise AuthStartupContainerUnavailableError()
        self._validator.validate()

    @override
    def stop(self) -> None:
        """Signal validation service shutdown."""
        if self._stop_event is not None:
            self._stop_event.set()
