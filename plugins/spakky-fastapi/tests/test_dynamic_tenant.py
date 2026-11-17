"""Request-resolved tenant authorization through the FastAPI boundary."""

from collections.abc import AsyncGenerator
from typing import Any, override

import pytest
import spakky.auth
from fastapi import FastAPI
from fastapi.testclient import TestClient
from spakky.auth import (
    AuthCapability,
    AuthContext,
    AuthInvocation,
    CredentialCarrier,
    AuthProviderContribution,
    AuthSubject,
    AuthorizationDecision,
    AuthorizationReasonCode,
    IAsyncRoleChecker,
    IAuthenticationProvider,
    RoleCheckRequest,
)
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod
from starlette.websockets import WebSocketDisconnect

import spakky.plugins.fastapi
from spakky.plugins.fastapi.auth import WEBSOCKET_AUTH_CHALLENGE_CLOSE_CODE
from spakky.plugins.fastapi.error import Forbidden
from tests import apps

MEMBER_WORKSPACE = "workspace-1"


@Pod()
class WorkspaceMembershipRoleChecker(IAsyncRoleChecker):
    """Async role checker that allows members of one workspace."""

    requests: list[RoleCheckRequest]

    def __init__(self) -> None:
        self.requests = []

    @override
    async def check_role(self, request: RoleCheckRequest) -> AuthorizationDecision:
        self.requests.append(request)
        if request.tenant == MEMBER_WORKSPACE:
            return AuthorizationDecision.allow()
        return AuthorizationDecision.deny(AuthorizationReasonCode.INSUFFICIENT_ROLE)


@Pod()
class RecordingAuthenticationProvider(IAuthenticationProvider):
    """Authentication provider that keeps the invocations it was given."""

    invocations: list[AuthInvocation]

    def __init__(self) -> None:
        self.invocations = []

    @override
    def authenticate(
        self,
        credential: CredentialCarrier,
        invocation: AuthInvocation,
    ) -> AuthContext:
        self.invocations.append(invocation)
        return AuthContext(
            subject=AuthSubject(id=credential.material),
            issuer=invocation.boundary,
        )


@Pod(name="test_auth_provider_contribution")
def auth_provider_contribution() -> AuthProviderContribution:
    return AuthProviderContribution(
        provider_id="test",
        capabilities=frozenset(
            {AuthCapability.AUTHENTICATION, AuthCapability.ROLE_CHECK}
        ),
    )


@pytest.fixture(name="auth_app", scope="function")
async def get_auth_app_fixture(name: str) -> AsyncGenerator[SpakkyApplication, Any]:
    @Pod(name="key")
    def get_name() -> str:
        return name

    app = (
        SpakkyApplication(ApplicationContext())
        .load_plugins(
            include={
                spakky.auth.PLUGIN_NAME,
                spakky.plugins.fastapi.PLUGIN_NAME,
            }
        )
        .scan(apps)
        .add(get_name)
        .add(RecordingAuthenticationProvider)
        .add(WorkspaceMembershipRoleChecker)
        .add(auth_provider_contribution)
    )
    app.start()
    yield app


@pytest.fixture(name="auth_api", scope="function")
def get_auth_api_fixture(auth_app: SpakkyApplication) -> FastAPI:
    return auth_app.container.get(type_=FastAPI)


@pytest.fixture(name="role_checker", scope="function")
def get_role_checker_fixture(
    auth_app: SpakkyApplication,
) -> WorkspaceMembershipRoleChecker:
    return auth_app.container.get(type_=WorkspaceMembershipRoleChecker)


def test_http_dynamic_tenant_from_header_expect_async_role_check_with_header_value(
    auth_api: FastAPI,
    role_checker: WorkspaceMembershipRoleChecker,
) -> None:
    """요청 헤더의 workspace가 tenant로 해석되어 비동기 role checker에 전달된다."""
    with TestClient(auth_api) as client:
        response = client.get(
            "/dummy/auth/workspace-member",
            headers={
                "Authorization": "Bearer subject-1",
                "X-Workspace": MEMBER_WORKSPACE,
            },
        )

    assert response.status_code == 200
    assert response.text == "member"
    assert [(request.role, request.tenant) for request in role_checker.requests] == [
        ("member", MEMBER_WORKSPACE)
    ]


def test_http_dynamic_tenant_of_other_workspace_expect_forbidden(
    auth_api: FastAPI,
) -> None:
    """소속이 아닌 workspace를 헤더로 보내면 403이다."""
    with TestClient(auth_api) as client:
        response = client.get(
            "/dummy/auth/workspace-member",
            headers={"Authorization": "Bearer subject-1", "X-Workspace": "other"},
        )

    assert response.status_code == Forbidden.status_code


def test_http_dynamic_tenant_without_header_expect_forbidden_before_role_check(
    auth_api: FastAPI,
    role_checker: WorkspaceMembershipRoleChecker,
) -> None:
    """tenant 헤더가 없으면 role checker를 부르지 않고 403으로 거부한다."""
    with TestClient(auth_api) as client:
        response = client.get(
            "/dummy/auth/workspace-member",
            headers={"Authorization": "Bearer subject-1"},
        )

    assert response.status_code == Forbidden.status_code
    assert role_checker.requests == []


def test_http_dynamic_tenant_from_path_parameter_expect_role_check_with_path_value(
    auth_api: FastAPI,
    role_checker: WorkspaceMembershipRoleChecker,
) -> None:
    """경로 파라미터도 tenant로 해석할 수 있다."""
    with TestClient(auth_api) as client:
        response = client.get(
            f"/dummy/auth/workspaces/{MEMBER_WORKSPACE}",
            headers={"Authorization": "Bearer subject-1"},
        )

    assert response.status_code == 200
    assert role_checker.requests[0].tenant == MEMBER_WORKSPACE


def test_websocket_dynamic_tenant_from_query_expect_connection_accepted(
    auth_api: FastAPI,
) -> None:
    """WebSocket은 query parameter에서 tenant를 해석한다."""
    client = TestClient(auth_api)
    with client.websocket_connect(
        f"/dummy/ws-workspace-member?access_token=subject-1&workspace={MEMBER_WORKSPACE}"
    ) as socket:
        assert socket.receive_text() == "member"


def test_websocket_dynamic_tenant_of_other_workspace_expect_policy_close(
    auth_api: FastAPI,
) -> None:
    """소속이 아닌 workspace로 연결하면 WebSocket을 1008로 닫는다."""
    client = TestClient(auth_api)
    with pytest.raises(WebSocketDisconnect) as disconnect:
        with client.websocket_connect(
            "/dummy/ws-workspace-member?access_token=subject-1&workspace=other"
        ):
            pass  # pragma: no cover - the handshake is rejected before this body

    assert disconnect.value.code == WEBSOCKET_AUTH_CHALLENGE_CLOSE_CODE


def test_http_invocation_attributes_expect_request_values_without_credentials(
    auth_app: SpakkyApplication,
    auth_api: FastAPI,
) -> None:
    """AuthInvocation은 헤더·경로·query 값을 담고 자격 증명은 담지 않는다."""
    provider = auth_app.container.get(type_=RecordingAuthenticationProvider)
    with TestClient(auth_api) as client:
        client.get(
            f"/dummy/auth/workspaces/{MEMBER_WORKSPACE}?page=2&page=3",
            headers={
                "Authorization": "Bearer subject-1",
                "Cookie": "session=secret",
                "X-Workspace": "from-header",
            },
        )

    invocation = provider.invocations[0]
    attributes = {
        attribute.name: attribute.value for attribute in invocation.attributes
    }
    assert invocation.operation == f"GET /dummy/auth/workspaces/{MEMBER_WORKSPACE}"
    assert str(attributes["handler"]).endswith("workspace_path_member_dummy")
    assert attributes["http.header.x-workspace"] == "from-header"
    assert attributes["http.path.workspace_id"] == MEMBER_WORKSPACE
    assert attributes["http.query.page"] == "2"
    assert "http.header.authorization" not in attributes
    assert "http.header.cookie" not in attributes
