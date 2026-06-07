from http import HTTPStatus
from inspect import Parameter
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from spakky.auth import AbstractSpakkyAuthError
from spakky.core.application.application_context import ApplicationContext
from spakky.plugins.fastapi.auth import (
    HTTP_AUTH_REQUEST_PARAMETER,
    FastAPIAuthBoundary,
)

from spakky.plugins.fastapi.error import (
    BadRequest,
    Forbidden,
    InternalServerError,
    Unauthorized,
)


class FallbackAuthError(AbstractSpakkyAuthError):
    """Auth error used to exercise the generic FastAPI auth mapping."""

    message = "Fallback auth error"


def test_get(api: FastAPI) -> None:
    """GET 요청이 정상적으로 처리됨을 검증한다."""
    with TestClient(api) as client:
        response = client.get("/dummy")
        assert response.status_code == HTTPStatus.OK
        assert response.text == "Hello World!"


def test_get_named_endpoint_with_explicit_name_and_description(api: FastAPI) -> None:
    """명시적 name과 description이 있는 엔드포인트가 정상 동작함을 검증한다."""
    with TestClient(api) as client:
        response = client.get("/dummy/named")
        assert response.status_code == HTTPStatus.OK
        assert response.text == "Named!"


def test_sync_route_handler_returns_response(api: FastAPI) -> None:
    """Ordinary sync route handlers return their result without being awaited."""
    with TestClient(api) as client:
        response = client.get("/dummy/sync")
        assert response.status_code == HTTPStatus.OK
        assert response.json() == {"message": "sync ok"}


def test_post(api: FastAPI) -> None:
    """POST 요청으로 JSON 데이터를 전송하고 응답을 받을 수 있음을 검증한다."""
    with TestClient(api) as client:
        response = client.post("/dummy", json={"name": "John", "age": 30})
        assert response.status_code == HTTPStatus.OK
        assert response.json() == {"name": "John", "age": 30}


def test_put(api: FastAPI) -> None:
    """PUT 요청으로 리소스를 업데이트할 수 있음을 검증한다."""
    with TestClient(api) as client:
        response = client.put("/dummy", json={"name": "John", "age": 30})
        assert response.status_code == HTTPStatus.OK
        assert response.json() == {"name": "John", "age": 30}


def test_patch(api: FastAPI) -> None:
    """PATCH 요청으로 리소스를 부분 업데이트할 수 있음을 검증한다."""
    with TestClient(api) as client:
        response = client.patch("/dummy", json={"name": "John", "age": 30})
        assert response.status_code == HTTPStatus.OK
        assert response.json() == {"name": "John", "age": 30}


def test_delete(api: FastAPI) -> None:
    """DELETE 요청으로 리소스를 삭제할 수 있음을 검증한다."""
    with TestClient(api) as client:
        id: UUID = uuid4()
        response = client.delete(f"/dummy/{id}")
        assert response.status_code == HTTPStatus.OK
        assert response.text == f'"{id}"'


def test_head(api: FastAPI) -> None:
    """HEAD 요청이 정상적으로 처리됨을 검증한다."""
    with TestClient(api) as client:
        response = client.head("/dummy")
        assert response.status_code == HTTPStatus.OK


def test_options(api: FastAPI) -> None:
    """OPTIONS 요청이 정상적으로 처리됨을 검증한다."""
    with TestClient(api) as client:
        response = client.options("/dummy")
        assert response.status_code == HTTPStatus.OK
        assert response.text == "Hello Options!"


def test_file(api: FastAPI) -> None:
    """파일 응답이 정상적으로 반환됨을 검증한다."""
    with TestClient(api) as client:
        response = client.get("/dummy/file/dummy.txt")
        assert response.status_code == HTTPStatus.OK
        assert response.text == "Hello File!"


def test_file_without_response_class(api: FastAPI) -> None:
    """response_class 없이도 파일 응답이 정상적으로 반환됨을 검증한다."""
    with TestClient(api) as client:
        response = client.get("/dummy/file-without-response-class/dummy.txt")
        assert response.status_code == HTTPStatus.OK
        assert response.text == "Hello File!"


def test_websocket(api: FastAPI) -> None:
    """WebSocket 연결을 통해 메시지를 송수신할 수 있음을 검증한다."""
    client = TestClient(api)
    with client.websocket_connect("/dummy/ws") as socket:
        socket.send_text("Hello World!")
        received: str = socket.receive_text()
        assert received == "Hello World!"


def test_generic_auth_error_maps_to_internal_server_error() -> None:
    """분류되지 않은 auth domain 오류는 HTTP 500으로 매핑된다."""
    application_context = ApplicationContext()
    auth_boundary = FastAPIAuthBoundary(application_context, application_context)

    with pytest.raises(InternalServerError):
        auth_boundary.map_http_auth_error(FallbackAuthError())


def test_auth_signature_inserts_request_before_var_keyword() -> None:
    """custom signature는 **kwargs 앞에 FastAPI Request 주입 파라미터를 둔다."""
    application_context = ApplicationContext()
    auth_boundary = FastAPIAuthBoundary(application_context, application_context)

    async def boundary(**kwargs: object) -> None:
        return None

    custom_signature = auth_boundary.signature_with_request(boundary)
    parameters = tuple(custom_signature.parameters.values())

    assert parameters[0].name == HTTP_AUTH_REQUEST_PARAMETER
    assert parameters[0].annotation is Request
    assert parameters[0].kind is Parameter.KEYWORD_ONLY
    assert parameters[1].kind is Parameter.VAR_KEYWORD


def test_http_handler_can_still_use_request_parameter(api: FastAPI) -> None:
    """비인증 목적의 Request 파라미터는 wrapper를 거쳐도 handler에 전달된다."""
    with TestClient(api) as client:
        response = client.get("/dummy/request-path")
        assert response.status_code == HTTPStatus.OK
        assert response.text == "/dummy/request-path"


def test_http_protected_handler_uses_bearer_without_request_parameter(
    api: FastAPI,
) -> None:
    """보호된 HTTP handler는 Request 파라미터 없이 seeded AuthContext를 사용한다."""
    with TestClient(api) as client:
        response = client.get(
            "/dummy/auth/protected",
            headers={"Authorization": "Bearer subject-1"},
        )
        assert response.status_code == HTTPStatus.OK
        assert response.json() == {"subject": "subject-1", "issuer": "HTTP"}


def test_http_protected_handler_missing_credential_challenges(api: FastAPI) -> None:
    """보호된 HTTP handler는 credential이 없으면 fail-closed CHALLENGE로 매핑된다."""
    with TestClient(api) as client:
        response = client.get("/dummy/auth/protected")
        assert response.status_code == Unauthorized.status_code


def test_http_invalid_bearer_credential_challenges(api: FastAPI) -> None:
    """인증 실패는 HTTP 401 CHALLENGE로 매핑된다."""
    with TestClient(api) as client:
        response = client.get(
            "/dummy/auth/protected",
            headers={"Authorization": "Bearer invalid"},
        )
        assert response.status_code == Unauthorized.status_code


def test_http_empty_bearer_credential_challenges(api: FastAPI) -> None:
    """빈 Bearer credential은 missing credential과 동일하게 401로 매핑된다."""
    with TestClient(api) as client:
        response = client.get(
            "/dummy/auth/protected",
            headers={"Authorization": "Bearer "},
        )
        assert response.status_code == Unauthorized.status_code


def test_http_public_handler_allows_bad_credential(api: FastAPI) -> None:
    """decorator 없는 HTTP handler는 credential 오류와 무관하게 allow all이다."""
    with TestClient(api) as client:
        response = client.get("/dummy", headers={"Authorization": "Bearer invalid"})
        assert response.status_code == HTTPStatus.OK


def test_http_public_handler_allows_missing_provider(
    api_without_auth_provider: FastAPI,
) -> None:
    """decorator 없는 HTTP handler는 provider가 없어도 credential 때문에 실패하지 않는다."""
    with TestClient(api_without_auth_provider) as client:
        response = client.get(
            "/dummy",
            headers={"Authorization": "Bearer subject-1"},
        )
        assert response.status_code == HTTPStatus.OK


def test_http_auth_denial_maps_to_forbidden(api: FastAPI) -> None:
    """보호된 handler의 DENY auth failure는 HTTP 403으로 매핑된다."""
    with TestClient(api) as client:
        response = client.get(
            "/dummy/auth/denied",
            headers={"Authorization": "Bearer subject-1"},
        )
        assert response.status_code == Forbidden.status_code


def test_http_auth_internal_error_maps_to_error(api: FastAPI) -> None:
    """기타 auth domain 오류는 HTTP 500 ERROR로 매핑된다."""
    with TestClient(api) as client:
        response = client.get(
            "/dummy/auth/internal-error",
            headers={"Authorization": "Bearer subject-1"},
        )
        assert response.status_code == InternalServerError.status_code


def test_http_auth_provider_unavailable_maps_to_error(
    api_without_auth_provider: FastAPI,
) -> None:
    """인증 provider unavailable은 HTTP 500 ERROR로 매핑된다."""
    with TestClient(api_without_auth_provider) as client:
        response = client.get(
            "/dummy/auth/protected",
            headers={"Authorization": "Bearer subject-1"},
        )
        assert response.status_code == InternalServerError.status_code


def test_websocket_protected_handler_uses_query_credential(api: FastAPI) -> None:
    """보호된 WebSocket handler는 query credential로 AuthContext를 seed한다."""
    client = TestClient(api)
    with client.websocket_connect(
        "/dummy/ws-protected?access_token=subject-1"
    ) as socket:
        received: str = socket.receive_text()
        assert received == "subject-1"


def test_websocket_protected_handler_uses_authorization_header(api: FastAPI) -> None:
    """보호된 WebSocket handler는 Authorization header credential을 우선 사용한다."""
    client = TestClient(api)
    with client.websocket_connect(
        "/dummy/ws-protected?access_token=query-subject",
        headers={"Authorization": "Bearer header-subject"},
    ) as socket:
        received: str = socket.receive_text()
        assert received == "header-subject"


def test_websocket_provider_unavailable_closes_as_error(
    api_without_auth_provider: FastAPI,
) -> None:
    """WebSocket provider unavailable은 ERROR close code로 매핑된다."""
    client = TestClient(api_without_auth_provider)
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(
            "/dummy/ws-protected",
            headers={"Authorization": "Bearer subject-1"},
        ) as socket:
            socket.receive_text()
    assert exc_info.value.code == 1011


def test_websocket_public_handler_allows_missing_provider(
    api_without_auth_provider: FastAPI,
) -> None:
    """decorator 없는 WebSocket handler는 provider가 없어도 credential 때문에 실패하지 않는다."""
    client = TestClient(api_without_auth_provider)
    with client.websocket_connect(
        "/dummy/ws",
        headers={"Authorization": "Bearer subject-1"},
    ) as socket:
        socket.send_text("Hello World!")
        received: str = socket.receive_text()
        assert received == "Hello World!"


def test_websocket_public_handler_allows_bad_credential(api: FastAPI) -> None:
    """decorator 없는 WebSocket handler는 credential 오류와 무관하게 allow all이다."""
    client = TestClient(api)
    with client.websocket_connect(
        "/dummy/ws",
        headers={"Authorization": "Bearer invalid"},
    ) as socket:
        socket.send_text("Hello World!")
        received: str = socket.receive_text()
        assert received == "Hello World!"


def test_websocket_protected_handler_missing_credential_closes(api: FastAPI) -> None:
    """보호된 WebSocket connection은 auth failure 시 close된다."""
    client = TestClient(api)
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/dummy/ws-protected") as socket:
            socket.receive_text()
    assert exc_info.value.code == 1008


def test_websocket_protected_handler_invalid_credential_closes(api: FastAPI) -> None:
    """보호된 WebSocket handler의 invalid credential은 CHALLENGE close로 매핑된다."""
    client = TestClient(api)
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(
            "/dummy/ws-protected",
            headers={"Authorization": "Bearer invalid"},
        ) as socket:
            socket.receive_text()
    assert exc_info.value.code == 1008


def test_when_unexpected_error_occurred(api: FastAPI) -> None:
    """예상치 못한 에러 발생 시 InternalServerError가 반환됨을 검증한다."""
    with TestClient(api) as client:
        response = client.get(url="/dummy/error")
        assert response.status_code == InternalServerError.status_code
        assert response.json()["message"] == InternalServerError.message


def test_when_managed_error_occurred(api: FastAPI) -> None:
    """관리되는 에러(BadRequest) 발생 시 적절한 에러 응답이 반환됨을 검증한다."""
    with TestClient(api) as client:
        response = client.get(
            url="/dummy/verify-email",
            params={"email": "invalid"},
        )
        assert response.status_code == BadRequest.status_code
        assert "Invalid email" in response.json()["args"]


def test_when_unexpected_error_with_debug_mode(api: FastAPI) -> None:
    """debug 모드에서 예상치 못한 에러 발생 시 traceback이 출력됨을 검증한다."""
    # Temporarily enable debug mode
    original_debug = api.debug
    api.debug = True

    try:
        with TestClient(api, raise_server_exceptions=False) as client:
            response = client.get(url="/dummy/error")
            assert response.status_code == InternalServerError.status_code
            # In debug mode, the response still returns but traceback is printed to stderr
            assert "message" in response.json()
    finally:
        api.debug = original_debug
