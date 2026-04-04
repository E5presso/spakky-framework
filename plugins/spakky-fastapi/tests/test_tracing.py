"""TracingMiddleware 단위 및 통합 테스트."""

import re

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from spakky.tracing.context import TraceContext
from spakky.tracing.w3c_propagator import W3CTracePropagator

from spakky.plugins.fastapi.middlewares.tracing import TracingMiddleware
from spakky.plugins.fastapi.post_processors import (
    add_builtin_middlewares as middlewares_module,
)

TRACEPARENT_PATTERN = re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")
SAMPLE_TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
SAMPLE_TRACE_ID = "0af7651916cd43dd8448eb211c80319c"
SAMPLE_SPAN_ID = "b7ad6b7169203331"


def _create_app_with_tracing() -> FastAPI:
    """TracingMiddleware가 설정된 FastAPI 앱을 생성한다."""
    api = FastAPI()
    propagator = W3CTracePropagator()
    api.add_middleware(TracingMiddleware, propagator=propagator)
    return api


# --- 단위 테스트 ---


def test_tracing_middleware_with_traceparent_expect_child_span() -> None:
    """traceparent 헤더가 있는 요청 시 같은 trace_id의 child span이 응답에 포함됨을 검증한다."""
    api = _create_app_with_tracing()

    @api.get("/test")
    async def endpoint() -> JSONResponse:
        return JSONResponse({"ok": True})

    with TestClient(api) as client:
        response = client.get(
            "/test",
            headers={"traceparent": SAMPLE_TRACEPARENT},
        )

    assert response.status_code == 200
    response_traceparent = response.headers.get("traceparent")
    assert response_traceparent is not None
    assert TRACEPARENT_PATTERN.match(response_traceparent)

    parts = response_traceparent.split("-")
    assert parts[1] == SAMPLE_TRACE_ID
    assert parts[2] != SAMPLE_SPAN_ID


def test_tracing_middleware_without_traceparent_expect_new_root() -> None:
    """traceparent 헤더가 없는 요청 시 새로운 root trace가 생성됨을 검증한다."""
    api = _create_app_with_tracing()

    @api.get("/test")
    async def endpoint() -> JSONResponse:
        return JSONResponse({"ok": True})

    with TestClient(api) as client:
        response = client.get("/test")

    assert response.status_code == 200
    response_traceparent = response.headers.get("traceparent")
    assert response_traceparent is not None
    assert TRACEPARENT_PATTERN.match(response_traceparent)


def test_tracing_middleware_with_invalid_traceparent_expect_new_root() -> None:
    """잘못된 traceparent 헤더 시 새로운 root trace가 생성됨을 검증한다."""
    api = _create_app_with_tracing()

    @api.get("/test")
    async def endpoint() -> JSONResponse:
        return JSONResponse({"ok": True})

    with TestClient(api) as client:
        response = client.get(
            "/test",
            headers={"traceparent": "invalid-header"},
        )

    assert response.status_code == 200
    response_traceparent = response.headers.get("traceparent")
    assert response_traceparent is not None
    assert TRACEPARENT_PATTERN.match(response_traceparent)

    parts = response_traceparent.split("-")
    assert parts[1] != SAMPLE_TRACE_ID


def test_tracing_middleware_handler_access_context_expect_trace_context_available() -> (
    None
):
    """핸들러 내부에서 TraceContext.get()으로 현재 trace context에 접근 가능함을 검증한다."""
    api = _create_app_with_tracing()
    captured_trace_id: str | None = None
    captured_parent_span_id: str | None = None

    @api.get("/test")
    async def endpoint() -> JSONResponse:
        nonlocal captured_trace_id, captured_parent_span_id
        ctx = TraceContext.get()
        assert ctx is not None
        captured_trace_id = ctx.trace_id
        captured_parent_span_id = ctx.parent_span_id
        return JSONResponse({"ok": True})

    with TestClient(api) as client:
        response = client.get(
            "/test",
            headers={"traceparent": SAMPLE_TRACEPARENT},
        )

    assert response.status_code == 200
    assert captured_trace_id == SAMPLE_TRACE_ID
    assert captured_parent_span_id == SAMPLE_SPAN_ID


def test_tracing_middleware_clears_context_after_request_expect_none() -> None:
    """요청 완료 후 TraceContext가 정리됨을 검증한다."""
    api = _create_app_with_tracing()

    @api.get("/test")
    async def endpoint() -> JSONResponse:
        return JSONResponse({"ok": True})

    with TestClient(api) as client:
        client.get("/test", headers={"traceparent": SAMPLE_TRACEPARENT})

    assert TraceContext.get() is None


def test_tracing_middleware_clears_context_on_error_expect_none() -> None:
    """핸들러 예외 시에도 TraceContext가 정리됨을 검증한다."""
    api = _create_app_with_tracing()

    @api.get("/test")
    async def endpoint() -> JSONResponse:
        raise RuntimeError("test error")

    with TestClient(api, raise_server_exceptions=False) as client:
        client.get("/test", headers={"traceparent": SAMPLE_TRACEPARENT})

    assert TraceContext.get() is None


# --- PostProcessor 통합 테스트 ---


def test_post_processor_with_tracing_plugin_expect_traceparent_in_response() -> None:
    """spakky-tracing 플러그인 로드 시 응답에 traceparent 헤더가 포함됨을 검증한다."""
    from spakky.core.application.application import SpakkyApplication
    from spakky.core.application.application_context import ApplicationContext
    from spakky.core.pod.annotations.pod import Pod

    import spakky.plugins.fastapi
    import spakky.tracing
    from tests import apps

    @Pod(name="key")
    def get_name() -> str:
        return "test"

    @Pod(name="api")
    def get_api() -> FastAPI:
        return FastAPI(debug=True)

    app = (
        SpakkyApplication(ApplicationContext())
        .load_plugins(
            include={
                spakky.plugins.fastapi.PLUGIN_NAME,
                spakky.tracing.PLUGIN_NAME,
            }
        )
        .scan(apps)
        .add(get_name)
        .add(get_api)
    )
    app.start()

    api = app.container.get(type_=FastAPI)
    with TestClient(api) as client:
        response = client.get("/dummy")

    assert response.status_code == 200
    response_traceparent = response.headers.get("traceparent")
    assert response_traceparent is not None
    assert TRACEPARENT_PATTERN.match(response_traceparent)


def test_post_processor_without_tracing_flag_expect_no_traceparent() -> None:
    """_HAS_TRACING이 False일 때 응답에 traceparent 헤더가 포함되지 않음을 검증한다."""
    from spakky.core.application.application import SpakkyApplication
    from spakky.core.application.application_context import ApplicationContext
    from spakky.core.pod.annotations.pod import Pod

    import spakky.plugins.fastapi
    from tests import apps

    original = (
        middlewares_module._HAS_TRACING
    )  # pyrefly: ignore - conditional module variable from try/except ImportError
    middlewares_module._HAS_TRACING = False  # pyrefly: ignore - conditional module variable from try/except ImportError
    try:

        @Pod(name="key")
        def get_name() -> str:
            return "test"

        @Pod(name="api")
        def get_api() -> FastAPI:
            return FastAPI(debug=True)

        app = (
            SpakkyApplication(ApplicationContext())
            .load_plugins(
                include={
                    spakky.plugins.fastapi.PLUGIN_NAME,
                }
            )
            .scan(apps)
            .add(get_name)
            .add(get_api)
        )
        app.start()

        api = app.container.get(type_=FastAPI)
        with TestClient(api) as client:
            response = client.get("/dummy")

        assert response.status_code == 200
        assert "traceparent" not in response.headers
    finally:
        middlewares_module._HAS_TRACING = original  # pyrefly: ignore - conditional module variable from try/except ImportError
