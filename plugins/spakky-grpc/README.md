# spakky-grpc

Spakky Framework용 code-first gRPC 플러그인

## Installation

```bash
pip install spakky-grpc spakky-tracing
```

## Quick Start

```python
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Annotated

import grpc.aio
import spakky.plugins.grpc
import spakky.tracing
from your_project import apps
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod
from spakky.plugins.grpc.annotations.field import ProtoField
from spakky.plugins.grpc.decorators.rpc import RpcMethodType, rpc
from spakky.plugins.grpc.schema.registry import DescriptorRegistry
from spakky.plugins.grpc.stereotypes.grpc_controller import GrpcController


@dataclass
class HelloRequest:
    name: Annotated[str, ProtoField(number=1)]


@dataclass
class HelloReply:
    message: Annotated[str, ProtoField(number=1)]


@GrpcController(package="example.v1", service_name="GreeterService")
class GreeterController:
    @rpc(method_type=RpcMethodType.UNARY)
    async def say_hello(self, request: HelloRequest) -> HelloReply:
        return HelloReply(message=f"Hello, {request.name}!")


@Pod()
def get_descriptor_registry() -> DescriptorRegistry:
	return DescriptorRegistry()


@Pod()
def get_grpc_server() -> grpc.aio.Server:
	server = grpc.aio.server()
	server.add_insecure_port("127.0.0.1:50051")
	return server


app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins(
        include={
            spakky.plugins.grpc.PLUGIN_NAME,
            spakky.tracing.PLUGIN_NAME,
        }
    )
    .scan(apps)
    .add(get_descriptor_registry)
    .add(get_grpc_server)
)
app.start()
```

## Streaming RPC

네 가지 gRPC 패턴을 모두 지원합니다.

| RpcMethodType | 설명 |
|---|---|
| `UNARY` | 단일 요청, 단일 응답 |
| `SERVER_STREAMING` | 단일 요청, 스트림 응답 |
| `CLIENT_STREAMING` | 스트림 요청, 단일 응답 |
| `BIDI_STREAMING` | 양방향 스트리밍 |

client-streaming과 bidirectional-streaming 메서드는 `request_type`과 `response_type`을 명시하면 descriptor 생성이 안정적입니다.

## Type Mapping

| Python 타입 | Protobuf 타입 |
|---|---|
| `str` | `string` |
| `int` | `int64` |
| `float` | `double` |
| `bool` | `bool` |
| `bytes` | `bytes` |

모든 메시지 필드는 `Annotated[..., ProtoField(number=N)]` 형식으로 protobuf 필드 번호를 가져야 합니다.

## Interceptors

- `ErrorHandlingInterceptor`: `AbstractGrpcStatusError` 계열 예외를 대응하는 gRPC status code로 변환합니다.
- `TracingInterceptor`: `traceparent` 메타데이터를 추출하고 trailing metadata로 새 trace context를 주입합니다.

트레이싱을 사용하려면 `spakky-tracing` 플러그인도 함께 로드해야 합니다.

## Verified Scenarios

- unary RPC
- server-streaming RPC
- client-streaming RPC
- bidirectional streaming RPC
- managed gRPC error to status code mapping
- W3C Trace Context propagation

## Documentation

- 사용자 가이드: [../../docs/guides/grpc.md](../../docs/guides/grpc.md)
- API 레퍼런스: [../../docs/api/plugins/spakky-grpc.md](../../docs/api/plugins/spakky-grpc.md)

## License

MIT License
