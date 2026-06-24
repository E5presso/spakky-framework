# gRPC 통합

> `spakky-grpc`는 code-first 방식의 gRPC 서비스 통합을 제공합니다.
> pydantic `BaseModel`에서 protobuf descriptor를 자동 생성하며, `@GrpcController`와 `@rpc` 데코레이터로 선언적으로 gRPC 서비스를 정의합니다.

---

## 동작 원리

1. `@GrpcController`로 gRPC 서비스 컨트롤러를 선언
2. `@rpc`로 메서드를 RPC 엔드포인트로 마크
3. pydantic `BaseModel`으로 요청/응답 타입 정의 (`ProtoField`로 필드 번호를 명시하거나 생략하여 자동 번호 부여)
4. `DescriptorBuilder`가 Python 타입에서 protobuf descriptor를 자동 생성
5. PostProcessor들이 서비스 등록, 인터셉터 추가, 서버 바인딩을 자동 처리

---

## 설정

```bash
pip install spakky-grpc
```

`spakky-grpc`는 `spakky`, `spakky-tracing`, `grpcio`, `protobuf`, `pydantic>=2.4`, `pydantic-settings`에 의존합니다.

`spakky-grpc` 플러그인은 `GrpcConfig`, `GrpcServerSpec`, `DescriptorRegistry`를 기본 Pod로 등록합니다. 서버를 리슨하려면 bind address를 환경변수로 지정합니다. bind address가 비어 있으면 descriptor와 handler 등록은 가능하지만 네트워크 listener는 열지 않습니다.

```bash
export SPAKKY_GRPC_BIND_ADDRESSES='["127.0.0.1:50051"]'
```

```python
import spakky.plugins.grpc
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

import apps  # `@GrpcController`가 정의된 사용자 패키지


app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins(include={
        spakky.plugins.grpc.PLUGIN_NAME,
    })
    .scan(apps)
    .start()
)
```

---

## 서비스 정의

### @GrpcController

gRPC 서비스 컨트롤러를 선언합니다. `@Controller`의 서브클래스이므로 DI 컨테이너에 자동 등록됩니다.

```python
from spakky.plugins.grpc.stereotypes.grpc_controller import GrpcController

@GrpcController(package="example.user", service_name="UserService")
class UserServiceController:
    def __init__(self, user_service: UserService) -> None:
        self._user_service = user_service

    ...
```

### @rpc

메서드를 gRPC RPC 엔드포인트로 마크합니다. `RpcMethodType`으로 스트리밍 모드를 지정합니다.

```python
from spakky.plugins.grpc.decorators.rpc import rpc, RpcMethodType

@GrpcController(package="example.user", service_name="UserService")
class UserServiceController:
    @rpc(method_type=RpcMethodType.UNARY)
    async def get_user(self, request: GetUserRequest) -> GetUserResponse:
        user = await self._user_service.get_user(request.user_id)
        return GetUserResponse(user_id=user.uid, name=user.name)
```

### RpcMethodType

| 값 | 설명 |
|----|------|
| `UNARY` | 단일 요청, 단일 응답 |
| `SERVER_STREAMING` | 단일 요청, 스트림 응답 |
| `CLIENT_STREAMING` | 스트림 요청, 단일 응답 |
| `BIDI_STREAMING` | 양방향 스트리밍 |

---

## Code-First Protobuf

### ProtoField

pydantic `BaseModel` 필드에 protobuf 필드 번호를 명시적으로 지정할 때 사용하는 **선택적** 어노테이션입니다. `.proto` 파일 없이 Python 타입만으로 protobuf descriptor를 생성합니다. 메시지 타입은 **반드시 `pydantic.BaseModel` 서브클래스**여야 합니다.

**기본 동작 — 자동 번호 부여**: `ProtoField`를 생략하면 `DescriptorBuilder`가 필드 이름의 SHA-256 해시에서 protobuf 필드 번호를 자동으로 결정합니다. 이름에서 번호가 결정되므로 필드를 추가하거나 선언 순서를 바꿔도 기존 필드의 번호는 변하지 않아 와이어 호환성이 유지됩니다. 예약 구간 19000–19999는 자동으로 건너뜁니다.

```python
from pydantic import BaseModel

# ProtoField 없이 자동 번호 부여 — 필드 이름에서 결정론적으로 계산됨
class GetUserRequest(BaseModel):
    user_id: str

class GetUserResponse(BaseModel):
    user_id: str
    name: str
    email: str
```

**번호 명시 — `ProtoField(number=N)`**: 기존 `.proto` 계약과 번호를 맞춰야 하거나 번호를 직접 제어하고 싶은 경우에만 `ProtoField`로 번호를 지정합니다.

```python
from typing import Annotated
from pydantic import BaseModel
from spakky.plugins.grpc.annotations.field import ProtoField

class GetUserRequest(BaseModel):
    user_id: Annotated[str, ProtoField(number=1)]

class GetUserResponse(BaseModel):
    user_id: Annotated[str, ProtoField(number=1)]
    name: Annotated[str, ProtoField(number=2)]
    email: Annotated[str, ProtoField(number=3)]
```

### 지원되는 타입 매핑

`type_map` 모듈이 Python 타입을 protobuf 타입으로 자동 매핑합니다.

| Python 타입 | Protobuf 타입 |
|------------|--------------|
| `str` | `string` |
| `int` | `int64` |
| `float` | `double` |
| `bool` | `bool` |
| `bytes` | `bytes` |
| `list[T]` | `repeated T` |
| `T \| None` | `optional T` (proto3 optional) |
| 중첩 `BaseModel` | `message` (재귀적으로 중첩 descriptor 생성) |

지원되지 않는 타입은 `UnsupportedFieldTypeError`를 던집니다.

### DescriptorRegistry

protobuf descriptor를 캐싱하고 관리합니다. `DescriptorBuilder`가 Python 타입에서 descriptor를 자동 생성합니다.

---

## 인터셉터

### TracingInterceptor

`spakky-tracing`과 연동하여 gRPC 요청의 분산 트레이싱을 자동 처리합니다. 요청 메타데이터에서 `traceparent` 헤더를 추출하여 `TraceContext`를 복원합니다.

### ErrorHandlingInterceptor

`AbstractGrpcStatusError` 서브클래스를 적절한 gRPC 상태 코드로 자동 변환합니다. 처리되지 않은 예외는 `INTERNAL` 상태로 매핑됩니다.

---

## PostProcessor

`spakky-grpc` 플러그인이 제공하는 `GrpcServerSpec` Pod에 아래 세 PostProcessor가 순서대로 구성을 누적합니다. 실제 `grpc.aio.Server` 인스턴스는 `start()` 시점에 ApplicationContext의 이벤트 루프에서 `GrpcServerSpec.build()`로 생성됩니다.

| PostProcessor | Order | 역할 |
|--------------|-------|------|
| `RegisterServicesPostProcessor` | 0 | `@GrpcController`의 `@rpc` 메서드를 generic handler로 빌드하여 spec에 추가 |
| `AddInterceptorsPostProcessor` | 1 | `ErrorHandlingInterceptor`, `TracingInterceptor`를 spec에 추가 |
| `BindServerPostProcessor` | 2 | `GrpcServerService`를 ApplicationContext에 등록하여 spec 기반으로 서버를 생성·시작·종료 |

---

## 에러 계층

### gRPC 상태 코드 에러

`AbstractGrpcStatusError`를 상속하며, 각 에러가 gRPC `StatusCode`에 매핑됩니다.

| 에러 | gRPC 상태 코드 | 설명 |
|------|---------------|------|
| `InvalidArgument` | `INVALID_ARGUMENT` | 잘못된 요청 인자 |
| `NotFound` | `NOT_FOUND` | 리소스 없음 |
| `AlreadyExists` | `ALREADY_EXISTS` | 리소스 이미 존재 |
| `PermissionDenied` | `PERMISSION_DENIED` | 권한 없음 |
| `Unauthenticated` | `UNAUTHENTICATED` | 인증 필요 |
| `FailedPrecondition` | `FAILED_PRECONDITION` | 사전 조건 미충족 |
| `Unavailable` | `UNAVAILABLE` | 서비스 이용 불가 |
| `InternalError` | `INTERNAL` | 내부 서버 에러 |

### 스키마 에러

| 에러 | 설명 |
|------|------|
| `UnsupportedFieldTypeError` | 지원하지 않는 protobuf 필드 타입 |
| `DescriptorAlreadyRegisteredError` | 이미 등록된 descriptor 재등록 시도 |

---

## End-to-End 예제

단일 서비스를 부트스트랩하고 `grpc.aio.insecure_channel`로 호출하는 완성 예제입니다.

### 서버 정의

```python
# apps/echo.py
from pydantic import BaseModel
from spakky.plugins.grpc.decorators.rpc import rpc
from spakky.plugins.grpc.stereotypes.grpc_controller import GrpcController


# ProtoField 없이 선언 — 필드 번호는 이름 해시에서 자동 부여됨
class EchoRequest(BaseModel):
    text: str


class EchoReply(BaseModel):
    text: str


@GrpcController(package="example.echo")
class EchoController:
    @rpc()
    async def echo(self, request: EchoRequest) -> EchoReply:
        return EchoReply(text=request.text)
```

### 부트스트랩

```python
# main.py
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

import spakky.plugins.grpc
import spakky.tracing

import apps


app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins(include={
        spakky.plugins.grpc.PLUGIN_NAME,
        spakky.tracing.PLUGIN_NAME,
    })
    .scan(apps)
)
app.start()
```

`SPAKKY_GRPC_BIND_ADDRESSES='["127.0.0.1:50051"]'`가 설정되어 있으면 `app.start()` 호출 시 PostProcessor 체인이 실행되어 `EchoController`의 핸들러와 인터셉터가 spec에 누적되고, `GrpcServerService`가 ApplicationContext의 이벤트 루프 스레드에서 `spec.build()`로 실제 서버를 생성한 뒤 `127.0.0.1:50051`에서 리슨합니다.

### 클라이언트 호출

클라이언트는 `DescriptorRegistry`에서 컴파일된 protobuf 메시지 클래스를 얻어 요청을 직렬화합니다.

```python
# client.py
import asyncio

import grpc.aio

from spakky.plugins.grpc.schema.registry import DescriptorRegistry


async def main(registry: DescriptorRegistry) -> None:
    request_cls = registry.get_message_class("example.echo.EchoRequest")
    reply_cls = registry.get_message_class("example.echo.EchoReply")

    async with grpc.aio.insecure_channel("127.0.0.1:50051") as channel:
        call = channel.unary_unary(
            "/example.echo.EchoController/echo",
            request_serializer=lambda msg: msg.SerializeToString(),
            response_deserializer=lambda data: reply_cls.FromString(data),
        )
        request = request_cls()
        request.text = "hello"
        reply = await call(request)
        print(reply.text)  # "hello"


asyncio.run(main(app.container.get(DescriptorRegistry)))
```

통합 테스트 전체 예제는 `plugins/spakky-grpc/tests/integration/`를 참고하세요. 유닛·에러·트레이싱 시나리오를 실제 `grpc.aio.Server`로 검증합니다.

## FastAPI `@ApiController`와의 비교

`@GrpcController`는 FastAPI 플러그인의 `@ApiController`와 동일한 설계 철학을 따릅니다. REST에서 gRPC로 이동할 때 참고하세요.

### 개념적으로 동일한 점

| 항목 | 설명 |
|------|------|
| 스테레오타입 데코레이터 | 둘 다 `@Controller`의 서브클래스. DI 컨테이너가 자동 인식 |
| 스캔 기반 자동 등록 | `SpakkyApplication.scan(...)`으로 컨트롤러 Pod를 탐색해 핸들러에 등록 |
| DI 주입 | 생성자 인자로 `@UseCase`·`@Repository` 등 다른 Pod를 주입받음 |
| AOP 적용 | `@Transactional`, `@logged` 등 AOP Aspect가 동일하게 동작 |

### gRPC 고유 차이점

| 항목 | 설명 |
|------|------|
| `SPAKKY_GRPC_BIND_ADDRESSES` | FastAPI와 마찬가지로 런타임 공유 객체는 플러그인이 제공하고, gRPC listener 주소만 환경 설정으로 지정함 |
| 메서드 시그니처 제약 | `@rpc` 메서드는 **요청 `BaseModel` 1개**만 파라미터로 받음. FastAPI처럼 path/query 파라미터를 분리하지 않음 (path·query 개념이 gRPC에 없음) |
| 메시지는 pydantic `BaseModel` | `pydantic.BaseModel` 서브클래스로 선언. 필드 번호는 이름 해시에서 자동 부여되며, `Annotated[T, ProtoField(number=N)]`으로 명시 지정도 가능. protobuf ↔ BaseModel 변환은 `google.protobuf.json_format` 브릿지로 수행 |
| 스트리밍 | `AsyncIterator[T]`를 요청/응답 타입으로 사용하여 4가지 스트리밍 패턴 지원 (FastAPI는 `StreamingResponse`로 단방향만) |
| 에러 → 상태 코드 매핑 | HTTP 상태 코드 대신 gRPC `StatusCode`. `AbstractGrpcStatusError` 서브클래스를 `ErrorHandlingInterceptor`가 매핑 |

## 다음 단계

- [DI & Pod](dependency-injection.md) — 의존성 주입 기본
- [분산 트레이싱](tracing.md) — TraceContext, Propagator
- [FastAPI 통합](fastapi.md) — REST 컨트롤러 (비교)
- [gRPC 심화](grpc-advanced.md) — Saga 응답 매핑과 운영 경계
