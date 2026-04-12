# spakky-grpc

Spakky Framework용 code-first gRPC 플러그인입니다.

Python dataclass와 어노테이션에서 protobuf descriptor를 생성하고,
gRPC 서비스 등록/인터셉터 연결을 자동화합니다.

## Installation

```bash
pip install spakky-grpc
```

## Quick Start

```python
from dataclasses import dataclass
from typing import Annotated

from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.plugins.grpc.annotations.field import ProtoField
from spakky.plugins.grpc.decorators.rpc import rpc
from spakky.plugins.grpc.stereotypes.grpc_controller import GrpcController


@dataclass
class HelloRequest:
	name: Annotated[str, ProtoField(number=1)]


@dataclass
class HelloReply:
	message: Annotated[str, ProtoField(number=1)]


@GrpcController(package="example.v1", service_name="GreeterService")
class GreeterController:
	@rpc(request_type=HelloRequest, response_type=HelloReply)
	async def say_hello(self, request: HelloRequest) -> HelloReply:
		return HelloReply(message=f"hello, {request.name}")


app = (
	SpakkyApplication(ApplicationContext())
	.load_plugins()
	.scan()
	.start()
)
```

## RPC Method Types

`@rpc`는 네 가지 gRPC 통신 패턴을 지원합니다.

- `RpcMethodType.UNARY`: 단일 요청, 단일 응답
- `RpcMethodType.SERVER_STREAMING`: 단일 요청, 스트리밍 응답
- `RpcMethodType.CLIENT_STREAMING`: 스트리밍 요청, 단일 응답
- `RpcMethodType.BIDI_STREAMING`: 양방향 스트리밍

권장사항:

- 스트리밍 메서드에서는 `request_type`, `response_type`을 명시적으로 지정
- 요청/응답 타입의 각 필드에 `ProtoField(number=...)` 지정

## Type Mapping

기본 Python 타입은 자동으로 protobuf 스칼라 타입으로 매핑됩니다.

| Python | Protobuf |
| --- | --- |
| `str` | `string` |
| `int` | `int64` |
| `float` | `double` |
| `bool` | `bool` |
| `bytes` | `bytes` |

`list[T]`, `Optional[T]`, nested dataclass도 descriptor 생성 시 처리됩니다.

## Interceptors

서버에는 기본적으로 다음 인터셉터가 연결됩니다.

- `ErrorHandlingInterceptor`: `AbstractGrpcStatusError` 계열 예외를 gRPC status로 매핑
- `TracingInterceptor`: `traceparent` 기반 컨텍스트 추출/전파

### Error Mapping

예를 들어 `NotFound`를 raise하면 클라이언트는 `NOT_FOUND` 상태를 받습니다.

### Tracing

요청 metadata의 `traceparent`를 읽어 child context를 만들고,
응답 trailing metadata에 최신 trace context를 주입합니다.

## Local Verification

패키지 루트에서 아래 순서로 검증할 수 있습니다.

```bash
uv run ruff check src/ tests/
uv run pyrefly check src/
uv run pytest tests/ -v
```

## License

MIT License
