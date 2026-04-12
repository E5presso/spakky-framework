import pytest

from tests.integration.conftest import GrpcIntegrationClient

SERVICE_PATH = "/integration.v1.IntegrationService"


@pytest.mark.asyncio
async def test_say_hello_when_unary_request_expect_greeting_response(
    grpc_client: GrpcIntegrationClient,
) -> None:
    """Unary RPC 호출이 실제 grpc.aio 서버에서 정상 응답함을 검증한다."""
    response, _call = await grpc_client.unary_unary(
        method_path=f"{SERVICE_PATH}/say_hello",
        request_full_name="integration.v1.HelloRequest",
        response_full_name="integration.v1.HelloReply",
        name="Spakky",
    )

    assert getattr(response, "message") == "Hello, Spakky!"
