"""Integration tests for the standard health and reflection services."""

from collections.abc import AsyncIterator

import grpc.aio
import pytest
from grpc_health.v1 import health_pb2
from grpc_reflection.v1alpha import reflection_pb2

HEALTH_CHECK_METHOD = "/grpc.health.v1.Health/Check"
REFLECTION_METHOD = "/grpc.reflection.v1alpha.ServerReflection/ServerReflectionInfo"
ECHO_SERVICE_NAME = "test.echo.EchoController"


@pytest.mark.asyncio
async def test_health_check_on_running_server_expect_serving(
    channel: grpc.aio.Channel,
) -> None:
    """The overall health status must answer SERVING so a native probe passes."""
    call = channel.unary_unary(
        HEALTH_CHECK_METHOD,
        request_serializer=lambda request: request.SerializeToString(),
        response_deserializer=health_pb2.HealthCheckResponse.FromString,
    )

    response = await call(health_pb2.HealthCheckRequest(service=""))

    assert response.status == health_pb2.HealthCheckResponse.SERVING


@pytest.mark.asyncio
async def test_health_check_for_registered_service_expect_serving(
    channel: grpc.aio.Channel,
) -> None:
    """A probe naming a registered service must pass, as k8s `grpc.service` does."""
    call = channel.unary_unary(
        HEALTH_CHECK_METHOD,
        request_serializer=lambda request: request.SerializeToString(),
        response_deserializer=health_pb2.HealthCheckResponse.FromString,
    )

    response = await call(health_pb2.HealthCheckRequest(service=ECHO_SERVICE_NAME))

    assert response.status == health_pb2.HealthCheckResponse.SERVING


@pytest.mark.asyncio
async def test_health_check_for_unknown_service_expect_not_found(
    channel: grpc.aio.Channel,
) -> None:
    """Probing a service with no reported status must fail with NOT_FOUND."""
    call = channel.unary_unary(
        HEALTH_CHECK_METHOD,
        request_serializer=lambda request: request.SerializeToString(),
        response_deserializer=health_pb2.HealthCheckResponse.FromString,
    )

    with pytest.raises(grpc.aio.AioRpcError) as raised:
        await call(health_pb2.HealthCheckRequest(service="never.registered"))

    assert raised.value.code() is grpc.StatusCode.NOT_FOUND


@pytest.mark.asyncio
async def test_reflection_list_services_expect_code_first_service(
    channel: grpc.aio.Channel,
) -> None:
    """Reflection must advertise the service built from the controller."""
    responses = await _reflect(
        channel, reflection_pb2.ServerReflectionRequest(list_services="")
    )

    advertised = {
        service.name for service in responses[0].list_services_response.service
    }
    assert ECHO_SERVICE_NAME in advertised


@pytest.mark.asyncio
async def test_reflection_describe_code_first_service_expect_file_descriptor(
    channel: grpc.aio.Channel,
) -> None:
    """Reflection must return the descriptor of a runtime-generated service."""
    responses = await _reflect(
        channel,
        reflection_pb2.ServerReflectionRequest(
            file_containing_symbol=ECHO_SERVICE_NAME
        ),
    )

    descriptors = responses[0].file_descriptor_response.file_descriptor_proto
    assert len(descriptors) == 1


@pytest.mark.asyncio
async def test_reflection_describe_health_service_expect_file_descriptor(
    channel: grpc.aio.Channel,
) -> None:
    """A service reflection advertises must also be describable through it."""
    responses = await _reflect(
        channel,
        reflection_pb2.ServerReflectionRequest(
            file_containing_symbol="grpc.health.v1.Health"
        ),
    )

    descriptors = responses[0].file_descriptor_response.file_descriptor_proto
    assert len(descriptors) == 1


async def _reflect(
    channel: grpc.aio.Channel, request: reflection_pb2.ServerReflectionRequest
) -> list[reflection_pb2.ServerReflectionResponse]:
    """Send one reflection request and drain the streamed responses."""

    async def _requests() -> AsyncIterator[reflection_pb2.ServerReflectionRequest]:
        yield request

    call = channel.stream_stream(
        REFLECTION_METHOD,
        request_serializer=lambda message: message.SerializeToString(),
        response_deserializer=reflection_pb2.ServerReflectionResponse.FromString,
    )
    return [response async for response in call(_requests())]
