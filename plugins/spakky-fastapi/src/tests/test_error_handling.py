from logging import getLogger

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from spakky_fastapi.middlewares.error_handling import ErrorHandlingMiddleware


def test_error_handling_middleware_debug_mode() -> None:
    """Test that ErrorHandlingMiddleware prints traceback in debug mode"""
    app = FastAPI()

    # Add middleware with debug=True
    middleware = ErrorHandlingMiddleware(app, logger=getLogger(__name__), debug=True)
    app.add_middleware(BaseHTTPMiddleware, dispatch=middleware.dispatch)

    @app.get("/error")
    async def error_endpoint() -> None:
        raise ValueError("Test error")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/error")
        assert response.status_code == 500
        assert "message" in response.json()


def test_error_handling_middleware_no_debug() -> None:
    """Test that ErrorHandlingMiddleware doesn't print traceback without debug mode"""
    app = FastAPI()

    # Add middleware with debug=False
    middleware = ErrorHandlingMiddleware(app, logger=getLogger(__name__), debug=False)
    app.add_middleware(BaseHTTPMiddleware, dispatch=middleware.dispatch)

    @app.get("/error")
    async def error_endpoint() -> None:
        raise ValueError("Test error")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/error")
        assert response.status_code == 500
        assert "message" in response.json()
