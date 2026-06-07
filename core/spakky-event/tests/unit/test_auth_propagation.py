"""Tests for outbound AuthContextSnapshot metadata propagation."""

from datetime import UTC, datetime, timedelta
from typing import override

import pytest
from spakky.auth import (
    AUTH_CONTEXT_CONTEXT_KEY,
    AUTH_CONTEXT_SNAPSHOT_METADATA_KEY,
    AuthContext,
    AuthContextSnapshot,
    AuthContextSnapshotSignature,
    AuthSnapshotPropagationConfig,
    AuthSubject,
    IAuthContextSnapshotSigner,
    InvalidAuthContextValueError,
    SnapshotSignRequest,
    store_auth_context,
)
from spakky.core.application.application_context import ApplicationContext

from spakky.event.auth_propagation import AuthContextSnapshotHeaderInjector
from spakky.event.error import (
    AuthSnapshotPropagationContextUnavailableError,
    AuthSnapshotPropagationSignerUnavailableError,
)


class FakeSnapshotSigner(IAuthContextSnapshotSigner):
    """Signer that records requests and returns a deterministic snapshot."""

    def __init__(self) -> None:
        self.requests: list[SnapshotSignRequest] = []

    @override
    def sign_snapshot(self, request: SnapshotSignRequest) -> AuthContextSnapshot:
        self.requests.append(request)
        return AuthContextSnapshot(
            subject=request.auth_context.subject,
            issuer=request.auth_context.issuer,
            issued_at=datetime(2026, 1, 1, tzinfo=UTC),
            expires_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=5),
            signature=AuthContextSnapshotSignature(
                key_id="kid-1",
                algorithm="HS256",
                signature="signature-1",
            ),
            tenant=request.auth_context.tenant,
        )


def _auth_context() -> AuthContext:
    return AuthContext(
        subject=AuthSubject(id="subject-1", display_name="Subject One"),
        issuer="issuer-1",
        tenant="tenant-1",
    )


def test_disabled_propagation_removes_raw_bearer_without_context() -> None:
    """disabled 상태에서도 raw bearer header는 제거하고 다른 header는 보존한다."""
    headers = {
        "Authorization": "Bearer raw-token",
        "x-custom": "value",
    }
    injector = AuthContextSnapshotHeaderInjector()

    injector.inject(headers)

    assert "Authorization" not in headers
    assert headers == {"x-custom": "value"}


def test_disabled_propagation_keeps_non_bearer_authorization() -> None:
    """raw bearer가 아닌 authorization header는 제거 대상이 아님을 검증한다."""
    headers = {"authorization": "Basic encoded"}
    injector = AuthContextSnapshotHeaderInjector()

    injector.inject(headers)

    assert headers == {"authorization": "Basic encoded"}


def test_enabled_propagation_without_application_context_fails_loudly() -> None:
    """enabled 상태에서 ApplicationContext가 없으면 조용히 누락하지 않는다."""
    injector = AuthContextSnapshotHeaderInjector(
        auth_snapshot_signer=FakeSnapshotSigner(),
        auth_snapshot_propagation_config=AuthSnapshotPropagationConfig(enabled=True),
    )

    with pytest.raises(AuthSnapshotPropagationContextUnavailableError):
        injector.inject({})


def test_enabled_propagation_without_auth_context_skips_snapshot() -> None:
    """public flow처럼 AuthContext가 없으면 snapshot header를 만들지 않는다."""
    signer = FakeSnapshotSigner()
    injector = AuthContextSnapshotHeaderInjector(
        auth_snapshot_signer=signer,
        auth_snapshot_propagation_config=AuthSnapshotPropagationConfig(enabled=True),
    )
    injector.set_application_context(ApplicationContext())
    headers: dict[str, str] = {}

    injector.inject(headers)

    assert signer.requests == []
    assert AUTH_CONTEXT_SNAPSHOT_METADATA_KEY not in headers


def test_enabled_propagation_with_invalid_context_value_fails() -> None:
    """ApplicationContext의 auth 값이 AuthContext가 아니면 auth 오류로 실패한다."""
    application_context = ApplicationContext()
    application_context.set_context_value(AUTH_CONTEXT_CONTEXT_KEY, "invalid")
    injector = AuthContextSnapshotHeaderInjector(
        auth_snapshot_signer=FakeSnapshotSigner(),
        auth_snapshot_propagation_config=AuthSnapshotPropagationConfig(enabled=True),
    )
    injector.set_application_context(application_context)

    with pytest.raises(InvalidAuthContextValueError):
        injector.inject({})


def test_enabled_propagation_without_signer_fails_loudly() -> None:
    """enabled 상태에서 signer가 없으면 snapshot 전파를 조용히 생략하지 않는다."""
    application_context = ApplicationContext()
    store_auth_context(application_context, _auth_context())
    injector = AuthContextSnapshotHeaderInjector(
        auth_snapshot_propagation_config=AuthSnapshotPropagationConfig(enabled=True),
    )
    injector.set_application_context(application_context)

    with pytest.raises(AuthSnapshotPropagationSignerUnavailableError):
        injector.inject({})


def test_enabled_propagation_injects_signed_snapshot_envelope() -> None:
    """enabled 상태에서 AuthContext를 signed snapshot envelope로 변환한다."""
    application_context = ApplicationContext()
    store_auth_context(application_context, _auth_context())
    signer = FakeSnapshotSigner()
    injector = AuthContextSnapshotHeaderInjector(
        auth_snapshot_signer=signer,
        auth_snapshot_propagation_config=AuthSnapshotPropagationConfig(enabled=True),
    )
    injector.set_application_context(application_context)
    headers: dict[str, str] = {}

    injector.inject(headers)

    assert len(signer.requests) == 1
    assert AUTH_CONTEXT_SNAPSHOT_METADATA_KEY in headers
