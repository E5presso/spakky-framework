# spakky-grpc

> [Spakky Framework](https://framework.spakky.com)를 위한 code-first gRPC 플러그인입니다.
> `@GrpcController`와 `@rpc` 선언을 gRPC service descriptor와 server binding으로 자동 변환합니다.

pydantic `BaseModel`로 메시지를 선언하고 `@GrpcController` + `@rpc` 데코레이터로 서비스를 정의하면, 런타임에 protobuf descriptor를 자동 생성하여 `grpc.aio.Server`에 등록합니다. `.proto` 파일이나 codegen 단계가 필요 없습니다. protobuf ↔ BaseModel 변환은 `google.protobuf.json_format` 브릿지(JSON 중간 표현)로 수행됩니다.

## 설치

```bash
pip install spakky-grpc
```

의존성: `grpcio`, `protobuf`, `pydantic>=2.4`, `spakky`, `spakky-auth`, `spakky-tracing`.

## 빠른 시작

```python
from typing import Annotated

from pydantic import BaseModel
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod

import spakky.plugins.grpc
from spakky.plugins.grpc.annotations.field import ProtoField
from spakky.plugins.grpc.decorators.rpc import rpc
from spakky.plugins.grpc.schema.registry import DescriptorRegistry
from spakky.plugins.grpc.server_spec import GrpcServerSpec
from spakky.plugins.grpc.stereotypes.grpc_controller import GrpcController

import apps  # `@GrpcController`-decorated classes live in your own package


class HelloRequest(BaseModel):
    name: Annotated[str, ProtoField(number=1)]


class HelloReply(BaseModel):
    message: Annotated[str, ProtoField(number=1)]


@GrpcController(package="example.hello")
class HelloController:
    @rpc()
    async def say_hello(self, request: HelloRequest) -> HelloReply:
        return HelloReply(message=f"Hello, {request.name}!")


@Pod()
def get_spec() -> GrpcServerSpec:
    spec = GrpcServerSpec()
    spec.add_insecure_port("127.0.0.1:50051")
    return spec


@Pod()
def get_registry() -> DescriptorRegistry:
    return DescriptorRegistry()


app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins(include={spakky.plugins.grpc.PLUGIN_NAME})
    .scan(apps)  # your package containing HelloController above
    .add(get_spec)
    .add(get_registry)
)
app.start()  # 서버가 별도 이벤트 루프 스레드에서 구동됩니다
```

`GrpcServerSpec`는 핸들러·인터셉터·바인드 주소를 누적합니다. 실제 `grpc.aio.Server`는 `ApplicationContext`의 이벤트 루프 스레드에서 `spec.build()`로 생성되므로 `grpc.aio` 내부 Future가 올바른 루프에 바인딩됩니다.

## 타입 매핑

`ProtoField` 어노테이션이 부착된 pydantic `BaseModel` 필드(`Annotated[T, ProtoField(number=N)]`)를 protobuf 필드로 매핑합니다. 필드 번호는 `BaseModel.model_fields[name].metadata`에서 읽어옵니다.

| Python | Protobuf |
|---|---|
| `str` | `string` |
| `int` | `int64` |
| `float` | `double` |
| `bool` | `bool` |
| `bytes` | `bytes` |
| `list[T]` | `repeated T` |
| `T \| None` | `optional T` |
| 중첩 `BaseModel` | `message` |

지원되지 않는 타입은 `UnsupportedFieldTypeError`를 던집니다.

## 스트리밍

`@rpc(method_type=...)`로 네 가지 gRPC 스트리밍 패턴을 모두 지원합니다.

| `RpcMethodType` | 시그니처 |
|---|---|
| `UNARY` | `async def m(self, req: Req) -> Resp` |
| `SERVER_STREAMING` | `async def m(self, req: Req) -> AsyncIterator[Resp]` |
| `CLIENT_STREAMING` | `async def m(self, reqs: AsyncIterator[Req]) -> Resp` |
| `BIDI_STREAMING` | `async def m(self, reqs: AsyncIterator[Req]) -> AsyncIterator[Resp]` |

## 인터셉터

플러그인이 자동으로 다음 인터셉터를 설치합니다.

| 인터셉터 | 조건 | 역할 |
|---|---|---|
| `ErrorHandlingInterceptor` | 항상 | 예외 → gRPC status 매핑 |
| `TracingInterceptor` | `spakky-tracing` 로드 시 | W3C Trace Context 전파 |

### 에러 매핑

`AbstractGrpcStatusError` 서브클래스의 `status_code`가 그대로 gRPC status로 전달됩니다.

| 에러 | gRPC Status |
|---|---|
| `InvalidArgument` | `INVALID_ARGUMENT` |
| `NotFound` | `NOT_FOUND` |
| `AlreadyExists` | `ALREADY_EXISTS` |
| `PermissionDenied` | `PERMISSION_DENIED` |
| `Unauthenticated` | `UNAUTHENTICATED` |
| `FailedPrecondition` | `FAILED_PRECONDITION` |
| `Unavailable` | `UNAVAILABLE` |
| `InternalError` | `INTERNAL` |

예상되지 않은 예외는 `INTERNAL`로 정규화됩니다.

### 인증 경계

gRPC 핸들러는 각 unary/stream 호출에서 `ApplicationContext.clear_context()`를 먼저 호출한 뒤, 사용자 컨트롤러 메서드 실행 전에 gRPC metadata의 인증 credential을 읽어 `spakky-auth`의 `AuthContext`를 request/context scope에 저장합니다.

지원 metadata:

| Metadata key | Credential |
|---|---|
| `authorization: Bearer <token>` | `CredentialCarrierKind.BEARER_TOKEN` |
| `spakky.auth.context_snapshot` | `CredentialCarrierKind.AUTH_CONTEXT_SNAPSHOT` |
| `x-spakky-auth-context-snapshot` | `CredentialCarrierKind.AUTH_CONTEXT_SNAPSHOT` |

credential이 있으면 `IAuthenticationProvider.authenticate()`가 `AuthInvocation(boundary="grpc", operation="/<package>.<service>/<method>")`와 함께 호출됩니다. 인증 제공자가 없으면 `UNAVAILABLE`로 fail-closed 됩니다. credential이 없는 public handler는 그대로 허용되며, `spakky-auth` 보호 데코레이터가 붙은 handler는 기존 AOP enforcement가 AuthContext 부재를 감지해 `UNAUTHENTICATED`로 실패합니다.

Auth error 매핑:

| Auth outcome | gRPC Status |
|---|---|
| `CHALLENGE` / 인증 실패 / AuthContext 없음 | `UNAUTHENTICATED` |
| `DENY` | `PERMISSION_DENIED` |
| provider unavailable | `UNAVAILABLE` |
| framework/config/evaluation error | `INTERNAL` |

### 트레이싱

`spakky-tracing` 플러그인을 함께 로드하면 W3C `traceparent` 메타데이터를 추출하여 `TraceContext.get()`으로 핸들러 내부에서 사용할 수 있고, 응답 trailing metadata에 자동 주입합니다.

```python
app.load_plugins(include={
    spakky.plugins.grpc.PLUGIN_NAME,
    spakky.tracing.PLUGIN_NAME,
})
```

## PostProcessor 실행 순서

| Order | PostProcessor | 역할 |
|---|---|---|
| 0 | `RegisterServicesPostProcessor` | `@GrpcController` → generic handler를 `GrpcServerSpec`에 추가 |
| 1 | `AddInterceptorsPostProcessor` | 에러/트레이싱 인터셉터를 `GrpcServerSpec`에 추가 |
| 2 | `BindServerPostProcessor` | `GrpcServerService`를 `ApplicationContext`에 등록 (start_async에서 `spec.build()`) |

## 라이선스

MIT License입니다. [Spakky Framework repository](https://github.com/E5presso/spakky-framework)를 참고하세요.
