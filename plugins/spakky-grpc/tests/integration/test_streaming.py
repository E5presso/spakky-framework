import pytest
from tests.integration.conftest import GrpcIntegrationClient

SERVICE_PATH = "/integration.v1.IntegrationService"


@pytest.mark.asyncio
async def test_stream_hello_when_server_streaming_request_expect_two_messages(
    grpc_client: GrpcIntegrationClient,
) -> None:
    """Server-streaming RPC가 순서대로 두 응답을 반환함을 검증한다."""
    responses, _call = await grpc_client.unary_stream(
        method_path=f"{SERVICE_PATH}/stream_hello",
        request_full_name="integration.v1.HelloRequest",
        response_full_name="integration.v1.HelloReply",
        name="Spakky",
    )

    assert [getattr(item, "message") for item in responses] == [
        "Hello, Spakky!",
        "Goodbye, Spakky!",
    ]


@pytest.mark.asyncio
async def test_collect_names_when_client_streaming_requests_expect_aggregated_response(
    grpc_client: GrpcIntegrationClient,
) -> None:
    """Client-streaming RPC가 요청 스트림을 집계해 단일 응답을 반환함을 검증한다."""
    response, _call = await grpc_client.stream_unary(
        method_path=f"{SERVICE_PATH}/collect_names",
        request_full_name="integration.v1.HelloRequest",
        response_full_name="integration.v1.NamesReply",
        request_values=[{"name": "alpha"}, {"name": "beta"}, {"name": "gamma"}],
    )

    assert getattr(response, "summary") == "alpha,beta,gamma"


@pytest.mark.asyncio
async def test_echo_names_when_bidirectional_streaming_requests_expect_echoed_messages(
    grpc_client: GrpcIntegrationClient,
) -> None:
    """Bidirectional streaming RPC가 각 요청에 대응하는 응답 스트림을 반환함을 검증한다."""
    responses, _call = await grpc_client.stream_stream(
        method_path=f"{SERVICE_PATH}/echo_names",
        request_full_name="integration.v1.HelloRequest",
        response_full_name="integration.v1.HelloReply",
        request_values=[{"name": "first"}, {"name": "second"}],
    )

    assert [getattr(item, "message") for item in responses] == [
        "FIRST",
        "SECOND",
    ]
