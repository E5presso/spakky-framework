from fastapi.testclient import TestClient
from spakky.plugins.fastapi.middlewares.error_handling import ErrorHandlingMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from fastapi import FastAPI


def test_error_handling_middleware_debug_mode() -> None:
    """ErrorHandlingMiddleware가 debug 모드에서 traceback을 출력함을 검증한다."""
    api = FastAPI()

    # Add middleware with debug=True
    middleware = ErrorHandlingMiddleware(api, debug=True)
    api.add_middleware(BaseHTTPMiddleware, dispatch=middleware.dispatch)

    @api.get("/error")
    async def error_endpoint() -> None:
        raise ValueError("Test error")

    with TestClient(api, raise_server_exceptions=False) as client:
        response = client.get("/error")
        assert response.status_code == 500
        assert "message" in response.json()


def test_error_handling_middleware_no_debug() -> None:
    """ErrorHandlingMiddleware가 debug 모드가 아닐 때 traceback을 출력하지 않음을 검증한다."""
    api = FastAPI()

    # Add middleware with debug=False
    middleware = ErrorHandlingMiddleware(api, debug=False)
    api.add_middleware(BaseHTTPMiddleware, dispatch=middleware.dispatch)

    @api.get("/error")
    async def error_endpoint() -> None:
        raise ValueError("Test error")

    with TestClient(api, raise_server_exceptions=False) as client:
        response = client.get("/error")
        assert response.status_code == 500
        assert "message" in response.json()
