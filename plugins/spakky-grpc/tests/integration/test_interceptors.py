import grpc
import pytest
from spakky.tracing.context import TraceContext
from tests.integration.conftest import GrpcIntegrationClient

SERVICE_PATH = "/integration.v1.IntegrationService"


@pytest.mark.asyncio
async def test_fail_invalid_argument_when_managed_error_raised_expect_grpc_status_code(
    grpc_client: GrpcIntegrationClient,
) -> None:
    """Managed gRPC 에러가 클라이언트에서 대응하는 status code로 관측됨을 검증한다."""
    with pytest.raises(grpc.aio.AioRpcError) as exc_info:
        await grpc_client.unary_unary(
            method_path=f"{SERVICE_PATH}/fail_invalid_argument",
            request_full_name="integration.v1.HelloRequest",
            response_full_name="integration.v1.HelloReply",
            name="boom",
        )

    assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    assert exc_info.value.details() == "Invalid Argument"


@pytest.mark.asyncio
async def test_capture_trace_when_traceparent_provided_expect_child_context_and_trailing_metadata(
    grpc_client: GrpcIntegrationClient,
) -> None:
    """traceparent 메타데이터가 컨트롤러와 trailing metadata까지 전파됨을 검증한다."""
    parent_context = TraceContext.new_root()
    response, call = await grpc_client.unary_unary(
        method_path=f"{SERVICE_PATH}/capture_trace",
        request_full_name="integration.v1.HelloRequest",
        response_full_name="integration.v1.TraceSnapshotReply",
        metadata=(("traceparent", parent_context.to_traceparent()),),
        name="trace",
    )

    assert getattr(response, "trace_id") == parent_context.trace_id
    assert getattr(response, "parent_span_id") == parent_context.span_id
    assert getattr(response, "span_id") != parent_context.span_id

    trailing_metadata = dict(await call.trailing_metadata())
    assert "traceparent" in trailing_metadata

    traceparent = trailing_metadata["traceparent"]
    if isinstance(traceparent, bytes):
        traceparent = traceparent.decode("utf-8")
    downstream_context = TraceContext.from_traceparent(traceparent)
    assert downstream_context.trace_id == parent_context.trace_id
