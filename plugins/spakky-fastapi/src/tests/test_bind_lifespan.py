from http import HTTPStatus

from fastapi.applications import FastAPI
from spakky.application.application import SpakkyApplication
from starlette.testclient import TestClient


def test_application_stopped_after_fastapi_shutdown(
    app: SpakkyApplication, api: FastAPI
) -> None:
    with TestClient(api) as client:
        response = client.get("/dummy")
        assert response.status_code == HTTPStatus.OK
        assert response.text == "Hello World!"

    assert app.application_context.is_started is False
