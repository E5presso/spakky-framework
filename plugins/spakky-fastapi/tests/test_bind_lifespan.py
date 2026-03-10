from http import HTTPStatus

from fastapi.applications import FastAPI
from spakky.core.application.application import SpakkyApplication
from starlette.testclient import TestClient


def test_application_stopped_after_fastapi_shutdown(
    app: SpakkyApplication, api: FastAPI
) -> None:
    """FastAPI 종료 후 SpakkyApplication이 정상적으로 중지됨을 검증한다."""
    with TestClient(api) as client:
        response = client.get("/dummy")
        assert response.status_code == HTTPStatus.OK
        assert response.text == "Hello World!"

    assert app.application_context.is_started is False
