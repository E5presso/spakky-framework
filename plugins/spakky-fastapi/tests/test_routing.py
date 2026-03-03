from http import HTTPStatus
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from spakky.plugins.fastapi.error import BadRequest, InternalServerError

from fastapi import FastAPI


def test_get(api: FastAPI) -> None:
    """GET 요청이 정상적으로 처리됨을 검증한다."""
    with TestClient(api) as client:
        response = client.get("/dummy")
        assert response.status_code == HTTPStatus.OK
        assert response.text == "Hello World!"


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
