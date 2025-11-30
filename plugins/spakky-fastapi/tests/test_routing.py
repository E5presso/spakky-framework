from http import HTTPStatus
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from spakky_fastapi.error import BadRequest, InternalServerError


def test_get(api: FastAPI) -> None:
    with TestClient(api) as client:
        response = client.get("/dummy")
        assert response.status_code == HTTPStatus.OK
        assert response.text == "Hello World!"


def test_post(api: FastAPI) -> None:
    with TestClient(api) as client:
        response = client.post("/dummy", json={"name": "John", "age": 30})
        assert response.status_code == HTTPStatus.OK
        assert response.json() == {"name": "John", "age": 30}


def test_put(api: FastAPI) -> None:
    with TestClient(api) as client:
        response = client.put("/dummy", json={"name": "John", "age": 30})
        assert response.status_code == HTTPStatus.OK
        assert response.json() == {"name": "John", "age": 30}


def test_patch(api: FastAPI) -> None:
    with TestClient(api) as client:
        response = client.patch("/dummy", json={"name": "John", "age": 30})
        assert response.status_code == HTTPStatus.OK
        assert response.json() == {"name": "John", "age": 30}


def test_delete(api: FastAPI) -> None:
    with TestClient(api) as client:
        id: UUID = uuid4()
        response = client.delete(f"/dummy/{id}")
        assert response.status_code == HTTPStatus.OK
        assert response.text == f'"{id}"'


def test_head(api: FastAPI) -> None:
    with TestClient(api) as client:
        response = client.head("/dummy")
        assert response.status_code == HTTPStatus.OK


def test_options(api: FastAPI) -> None:
    with TestClient(api) as client:
        response = client.options("/dummy")
        assert response.status_code == HTTPStatus.OK
        assert response.text == "Hello Options!"


def test_file(api: FastAPI) -> None:
    with TestClient(api) as client:
        response = client.get("/dummy/file/dummy.txt")
        assert response.status_code == HTTPStatus.OK
        assert response.text == "Hello File!"


def test_file_without_response_class(api: FastAPI) -> None:
    with TestClient(api) as client:
        response = client.get("/dummy/file-without-response-class/dummy.txt")
        assert response.status_code == HTTPStatus.OK
        assert response.text == "Hello File!"


def test_websocket(api: FastAPI) -> None:
    client = TestClient(api)
    with client.websocket_connect("/dummy/ws") as socket:
        socket.send_text("Hello World!")
        received: str = socket.receive_text()
        assert received == "Hello World!"


def test_when_unexpected_error_occurred(api: FastAPI) -> None:
    with TestClient(api) as client:
        response = client.get(url="/dummy/error")
        assert response.status_code == InternalServerError.status_code
        assert response.json()["message"] == InternalServerError.message


def test_when_managed_error_occurred(api: FastAPI) -> None:
    with TestClient(api) as client:
        response = client.get(
            url="/dummy/verify-email",
            params={"email": "invalid"},
        )
        assert response.status_code == BadRequest.status_code
        assert "Invalid email" in response.json()["args"]


def test_when_unexpected_error_with_debug_mode(api: FastAPI) -> None:
    """Test that debug mode prints traceback for unexpected errors"""
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
