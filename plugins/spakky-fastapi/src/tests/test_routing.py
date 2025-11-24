from http import HTTPStatus
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from spakky_fastapi.error import BadRequest, InternalServerError


def test_get(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.get("/dummy")
        assert response.status_code == HTTPStatus.OK
        assert response.text == "Hello World!"


def test_post(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.post("/dummy", json={"name": "John", "age": 30})
        assert response.status_code == HTTPStatus.OK
        assert response.json() == {"name": "John", "age": 30}


def test_put(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.put("/dummy", json={"name": "John", "age": 30})
        assert response.status_code == HTTPStatus.OK
        assert response.json() == {"name": "John", "age": 30}


def test_patch(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.patch("/dummy", json={"name": "John", "age": 30})
        assert response.status_code == HTTPStatus.OK
        assert response.json() == {"name": "John", "age": 30}


def test_delete(app: FastAPI) -> None:
    with TestClient(app) as client:
        id: UUID = uuid4()
        response = client.delete(f"/dummy/{id}")
        assert response.status_code == HTTPStatus.OK
        assert response.text == f'"{id}"'


def test_head(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.head("/dummy")
        assert response.status_code == HTTPStatus.OK


def test_options(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.options("/dummy")
        assert response.status_code == HTTPStatus.OK
        assert response.text == "Hello Options!"


def test_file(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.get("/dummy/file/dummy.txt")
        assert response.status_code == HTTPStatus.OK
        assert response.text == "Hello File!"


def test_file_without_response_class(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.get("/dummy/file-without-response-class/dummy.txt")
        assert response.status_code == HTTPStatus.OK
        assert response.text == "Hello File!"


def test_websocket(app: FastAPI) -> None:
    client = TestClient(app)
    with client.websocket_connect("/dummy/ws") as socket:
        socket.send_text("Hello World!")
        received: str = socket.receive_text()
        assert received == "Hello World!"


def test_when_unexpected_error_occurred(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.get(url="/dummy/error")
        assert response.status_code == InternalServerError.status_code
        assert response.json()["message"] == InternalServerError.message


def test_when_managed_error_occurred(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.get(
            url="/dummy/verify-email",
            params={"email": "invalid"},
        )
        assert response.status_code == BadRequest.status_code
        assert response.json()["message"] == "Invalid email"


def test_when_unexpected_error_with_debug_mode(app: FastAPI) -> None:
    """Test that debug mode prints traceback for unexpected errors"""
    # Temporarily enable debug mode
    original_debug = app.debug
    app.debug = True

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(url="/dummy/error")
            assert response.status_code == InternalServerError.status_code
            # In debug mode, the response still returns but traceback is printed to stderr
            assert "message" in response.json()
    finally:
        app.debug = original_debug
