import threading
from typing import override

import pytest

from spakky.auth import (
    AUTH_STARTUP_VALIDATION_ERROR_DETAIL_KEY,
    AuthCapability,
    AuthProviderContribution,
    AuthSnapshotPropagationConfig,
    AuthCapabilityStartupValidationService,
    AuthStartupCapabilityValidationError,
    AuthStartupContainerUnavailableError,
    protected,
    require_permission,
    require_policy,
    require_relation,
    require_role,
    require_scope,
)
from spakky.auth.main import initialize
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import (
    STARTUP_PHASE_SERVICE_START,
    ApplicationContext,
)
from spakky.core.pod.annotations.pod import Pod
from spakky.core.service.interfaces.service import IService


@Pod(name="protected_scope_boundary")
class ProtectedScopeBoundary:
    @require_scope("documents:read")
    def read(self) -> str:
        return "ok"


@protected
@Pod(name="class_and_method_protected_boundary")
class ClassAndMethodProtectedBoundary:
    @require_scope("documents:read")
    def read(self) -> str:
        return "ok"


@Pod(name="all_requirement_boundary")
class AllRequirementBoundary:
    @require_relation("owner", resource="document:1")
    @require_policy("document:1", "read")
    @require_permission("documents:read")
    @require_role("role:admin")
    @require_scope("documents:read")
    def read(self) -> str:
        return "ok"


@protected
@Pod(name="protected_function_boundary")
def protected_function_boundary() -> str:
    return "ok"


@Pod(name="unprotected_boundary")
class UnprotectedBoundary:
    def read(self) -> str:
        return "ok"


@Pod(name="user_service_after_auth_validation")
class UserServiceAfterAuthValidation(IService):
    started_count = 0

    _stop_event: threading.Event | None

    def __init__(self) -> None:
        self._stop_event = None

    @override
    def set_stop_event(self, stop_event: threading.Event) -> None:
        self._stop_event = stop_event

    @override
    def start(self) -> None:
        type(self).started_count += 1

    @override
    def stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()


@Pod(name="auth_provider_one")
def auth_provider_one() -> AuthProviderContribution:
    return AuthProviderContribution(
        provider_id="provider:one",
        capabilities=frozenset(
            {
                AuthCapability.AUTHENTICATION,
                AuthCapability.SCOPE_CHECK,
            }
        ),
    )


@Pod(name="auth_provider_two")
def auth_provider_two() -> AuthProviderContribution:
    return AuthProviderContribution(
        provider_id="provider:two",
        capabilities=frozenset(
            {
                AuthCapability.AUTHENTICATION,
                AuthCapability.SCOPE_CHECK,
            }
        ),
    )


@Pod(name="all_requirement_provider")
def all_requirement_provider() -> AuthProviderContribution:
    return AuthProviderContribution(
        provider_id="provider:all",
        capabilities=frozenset(
            {
                AuthCapability.AUTHENTICATION,
                AuthCapability.PERMISSION_CHECK,
                AuthCapability.POLICY_EVALUATION,
                AuthCapability.RELATION_CHECK,
                AuthCapability.ROLE_CHECK,
                AuthCapability.SCOPE_CHECK,
            }
        ),
    )


@Pod(name="snapshot_provider")
def snapshot_provider() -> AuthProviderContribution:
    return AuthProviderContribution(
        provider_id="provider:snapshot",
        capabilities=frozenset(
            {
                AuthCapability.SNAPSHOT_SIGN,
                AuthCapability.SNAPSHOT_VERIFY,
            }
        ),
    )


@Pod(name="enabled_snapshot_propagation_config")
def enabled_snapshot_propagation_config() -> AuthSnapshotPropagationConfig:
    return AuthSnapshotPropagationConfig(enabled=True)


@Pod(name="disabled_snapshot_propagation_config")
def disabled_snapshot_propagation_config() -> AuthSnapshotPropagationConfig:
    return AuthSnapshotPropagationConfig(enabled=False)


def test_auth_startup_validation_rejects_zero_providers_for_protected_usage() -> None:
    context = ApplicationContext()
    app = SpakkyApplication(context).enable_startup_diagnostics()
    initialize(app)
    app.add(ProtectedScopeBoundary)
    app.add(UserServiceAfterAuthValidation)
    UserServiceAfterAuthValidation.started_count = 0

    try:
        with pytest.raises(AuthStartupCapabilityValidationError) as raised:
            app.start()
    finally:
        if context.is_started:
            app.stop()

    capabilities = {item.capability for item in raised.value.diagnostics}
    provider_counts = {
        item.capability: item.provider_count for item in raised.value.diagnostics
    }
    records = {record.phase_name: record for record in app.startup_report.records}
    failure_summary = records[STARTUP_PHASE_SERVICE_START].failure_summary

    assert capabilities == {
        AuthCapability.AUTHENTICATION,
        AuthCapability.SCOPE_CHECK,
    }
    assert provider_counts[AuthCapability.AUTHENTICATION] == 0
    assert provider_counts[AuthCapability.SCOPE_CHECK] == 0
    assert UserServiceAfterAuthValidation.started_count == 0
    assert failure_summary is not None
    assert {detail.key for detail in failure_summary.diagnostic_details} == {
        AUTH_STARTUP_VALIDATION_ERROR_DETAIL_KEY
    }


def test_auth_startup_validation_accepts_single_provider_for_protected_usage() -> None:
    context = ApplicationContext()
    app = SpakkyApplication(context)
    initialize(app)
    app.add(auth_provider_one)
    app.add(ProtectedScopeBoundary)

    app.start()
    app.stop()


def test_auth_startup_validation_accepts_all_requirement_capabilities() -> None:
    context = ApplicationContext()
    app = SpakkyApplication(context)
    initialize(app)
    app.add(all_requirement_provider)
    app.add(AllRequirementBoundary)
    app.add(ClassAndMethodProtectedBoundary)
    app.add(protected_function_boundary)

    app.start()
    app.stop()


def test_auth_startup_validation_rejects_multiple_providers_for_capability() -> None:
    context = ApplicationContext()
    app = SpakkyApplication(context)
    initialize(app)
    app.add(auth_provider_one)
    app.add(auth_provider_two)
    app.add(ProtectedScopeBoundary)

    try:
        with pytest.raises(AuthStartupCapabilityValidationError) as raised:
            app.start()
    finally:
        if context.is_started:
            app.stop()

    provider_counts = {
        item.capability: item.provider_count for item in raised.value.diagnostics
    }

    assert provider_counts[AuthCapability.AUTHENTICATION] == 2
    assert provider_counts[AuthCapability.SCOPE_CHECK] == 2


def test_auth_startup_validation_allows_no_provider_without_protected_usage() -> None:
    context = ApplicationContext()
    app = SpakkyApplication(context)
    initialize(app)
    app.add(UnprotectedBoundary)

    app.start()
    app.stop()


def test_auth_startup_validation_allows_disabled_snapshot_propagation_without_provider() -> (
    None
):
    context = ApplicationContext()
    app = SpakkyApplication(context)
    initialize(app)
    app.add(disabled_snapshot_propagation_config)

    app.start()
    app.stop()


def test_auth_startup_validation_rejects_enabled_snapshot_propagation_without_provider() -> (
    None
):
    context = ApplicationContext()
    app = SpakkyApplication(context)
    initialize(app)
    app.add(enabled_snapshot_propagation_config)

    try:
        with pytest.raises(AuthStartupCapabilityValidationError) as raised:
            app.start()
    finally:
        if context.is_started:
            app.stop()

    assert {item.capability for item in raised.value.diagnostics} == {
        AuthCapability.SNAPSHOT_SIGN,
        AuthCapability.SNAPSHOT_VERIFY,
    }


def test_auth_startup_validation_accepts_enabled_snapshot_propagation_with_one_provider() -> (
    None
):
    context = ApplicationContext()
    app = SpakkyApplication(context)
    initialize(app)
    app.add(enabled_snapshot_propagation_config)
    app.add(snapshot_provider)

    app.start()
    app.stop()


def test_auth_startup_validation_service_without_container_expect_error() -> None:
    service = AuthCapabilityStartupValidationService()

    with pytest.raises(AuthStartupContainerUnavailableError):
        service.start()


def test_auth_startup_validation_service_stop_without_event_expect_noop() -> None:
    service = AuthCapabilityStartupValidationService()

    service.stop()
