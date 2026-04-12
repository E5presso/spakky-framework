"""Integration tests for error mapping and trace-context propagation."""

import re

import grpc
import grpc.aio
import pytest
from spakky.core.application.application import SpakkyApplication

from spakky.plugins.grpc.schema.registry import DescriptorRegistry
from spakky.plugins.grpc.server_spec import GrpcServerSpec
from tests.integration._client import deserializer_for, serializer_for
from tests.integration.apps.echo import (
    EchoReply,
    EchoRequest,
    ErrorRequest,
    TraceReply,
)

PACKAGE = "test.echo"
RAISE_METHOD = "/test.echo.EchoController/raise_error"
TRACE_METHOD = "/test.echo.EchoController/capture_trace"
TRACE_MISSING = "__missing__"
TRACEPARENT_PATTERN = re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")
SAMPLE_TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
SAMPLE_TRACE_ID = "0af7651916cd43dd8448eb211c80319c"
SAMPLE_SPAN_ID = "b7ad6b7169203331"


@pytest.mark.parametrize(
    ("code", "expected_status"),
    [
        ("invalid_argument", grpc.StatusCode.INVALID_ARGUMENT),
        ("not_found", grpc.StatusCode.NOT_FOUND),
        ("already_exists", grpc.StatusCode.ALREADY_EXISTS),
        ("permission_denied", grpc.StatusCode.PERMISSION_DENIED),
        ("unauthenticated", grpc.StatusCode.UNAUTHENTICATED),
        ("failed_precondition", grpc.StatusCode.FAILED_PRECONDITION),
        ("unavailable", grpc.StatusCode.UNAVAILABLE),
        ("internal", grpc.StatusCode.INTERNAL),
    ],
)
@pytest.mark.asyncio
async def test_raise_error_with_mapped_status_expect_matching_grpc_code(
    channel: grpc.aio.Channel,
    registry: DescriptorRegistry,
    code: str,
    expected_status: grpc.StatusCode,
) -> None:
    """AbstractGrpcStatusError subclasses should surface as their declared status."""
    call = channel.unary_unary(
        RAISE_METHOD,
        request_serializer=serializer_for(registry, f"{PACKAGE}.ErrorRequest"),
        response_deserializer=deserializer_for(
            registry, f"{PACKAGE}.EchoReply", EchoReply
        ),
    )

    with pytest.raises(grpc.aio.AioRpcError) as excinfo:
        await call(ErrorRequest(code=code))

    assert excinfo.value.code() == expected_status


@pytest.mark.asyncio
async def test_raise_error_with_unexpected_exception_expect_internal_status(
    channel: grpc.aio.Channel, registry: DescriptorRegistry
) -> None:
    """Non-spakky exceptions should be normalised to INTERNAL."""
    call = channel.unary_unary(
        RAISE_METHOD,
        request_serializer=serializer_for(registry, f"{PACKAGE}.ErrorRequest"),
        response_deserializer=deserializer_for(
            registry, f"{PACKAGE}.EchoReply", EchoReply
        ),
    )

    with pytest.raises(grpc.aio.AioRpcError) as excinfo:
        await call(ErrorRequest(code="__unknown__"))

    assert excinfo.value.code() == grpc.StatusCode.INTERNAL


@pytest.mark.asyncio
async def test_capture_trace_with_traceparent_expect_child_span_on_server(
    channel: grpc.aio.Channel, registry: DescriptorRegistry
) -> None:
    """Sending ``traceparent`` should activate a child span for the handler."""
    call = channel.unary_unary(
        TRACE_METHOD,
        request_serializer=serializer_for(registry, f"{PACKAGE}.EchoRequest"),
        response_deserializer=deserializer_for(
            registry, f"{PACKAGE}.TraceReply", TraceReply
        ),
    )

    rpc_call = call(
        EchoRequest(text="ignored"), metadata=(("traceparent", SAMPLE_TRACEPARENT),)
    )
    reply = await rpc_call

    assert isinstance(reply, TraceReply)
    assert reply.trace_id == SAMPLE_TRACE_ID
    assert reply.parent_span_id == SAMPLE_SPAN_ID

    trailing = await rpc_call.trailing_metadata()
    headers = {key: value for key, value in trailing}
    assert "traceparent" in headers
    parts = headers["traceparent"].split("-")
    assert parts[1] == SAMPLE_TRACE_ID
    assert parts[2] != SAMPLE_SPAN_ID


@pytest.mark.asyncio
async def test_capture_trace_without_traceparent_expect_new_root_trace(
    channel: grpc.aio.Channel, registry: DescriptorRegistry
) -> None:
    """Missing ``traceparent`` should yield a freshly generated root trace."""
    call = channel.unary_unary(
        TRACE_METHOD,
        request_serializer=serializer_for(registry, f"{PACKAGE}.EchoRequest"),
        response_deserializer=deserializer_for(
            registry, f"{PACKAGE}.TraceReply", TraceReply
        ),
    )

    rpc_call = call(EchoRequest(text="ignored"))
    reply = await rpc_call

    assert isinstance(reply, TraceReply)
    assert reply.trace_id != TRACE_MISSING
    assert reply.parent_span_id == ""

    trailing = await rpc_call.trailing_metadata()
    headers = {key: value for key, value in trailing}
    assert "traceparent" in headers
    assert TRACEPARENT_PATTERN.match(headers["traceparent"])


@pytest.mark.asyncio
async def test_capture_trace_without_tracing_plugin_expect_no_context(
    app_without_tracing: SpakkyApplication,
) -> None:
    """With the tracing plugin disabled no ``TraceContext`` should be active."""
    registry = app_without_tracing.container.get(DescriptorRegistry)
    port = app_without_tracing.container.get(GrpcServerSpec).bound_ports[0]

    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    try:
        call = channel.unary_unary(
            TRACE_METHOD,
            request_serializer=serializer_for(registry, f"{PACKAGE}.EchoRequest"),
            response_deserializer=deserializer_for(
                registry, f"{PACKAGE}.TraceReply", TraceReply
            ),
        )

        rpc_call = call(EchoRequest(text="ignored"))
        reply = await rpc_call

        assert isinstance(reply, TraceReply)
        assert reply.trace_id == TRACE_MISSING
        trailing = await rpc_call.trailing_metadata()
        headers = {key: value for key, value in (trailing or ())}
        assert "traceparent" not in headers
    finally:
        await channel.close()
