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

`spakky-grpc`는 `spakky`, `spakky-auth`, `spakky-tracing`, `grpcio`, `grpcio-health-checking`, `grpcio-reflection`, `protobuf`, `pydantic>=2.4`, `pydantic-settings`에 의존합니다.

`spakky-grpc` 플러그인은 `GrpcConfig`, `GrpcServerSpec`, `DescriptorRegistry`, 헬스체크 servicer를 기본 Pod로 등록합니다. 서버를 리슨하려면 bind address를 환경변수로 지정합니다. bind address가 비어 있으면 descriptor와 handler 등록은 가능하지만 네트워크 listener는 열지 않습니다.

```bash
export SPAKKY_GRPC_BIND_ADDRESSES='["127.0.0.1:50051"]'
```

모든 설정은 `SPAKKY_GRPC_` 접두사 환경변수로 주입합니다.

| 환경변수 | 기본값 | 역할 |
|---|---|---|
| `SPAKKY_GRPC_BIND_ADDRESSES` | `()` | listener 주소 목록 (`host:port`) |
| `SPAKKY_GRPC_SERVER_OPTIONS` | `{}` | `grpc.aio.server(options=...)`로 전달되는 채널 인자 |
| `SPAKKY_GRPC_TLS_CERTIFICATE_CHAIN_FILE` | `None` | 서버 인증서 체인 PEM 파일 |
| `SPAKKY_GRPC_TLS_PRIVATE_KEY_FILE` | `None` | 인증서 체인에 대응하는 개인키 PEM 파일 |
| `SPAKKY_GRPC_TLS_CLIENT_CA_FILE` | `None` | 클라이언트 인증서를 서명한 CA PEM 파일 |
| `SPAKKY_GRPC_REQUIRE_CLIENT_AUTH` | `false` | 클라이언트 인증서 제시 강제 여부 |
| `SPAKKY_GRPC_HEALTH_SERVICE_ENABLED` | `true` | `grpc.health.v1.Health` 노출 여부 |
| `SPAKKY_GRPC_REFLECTION_SERVICE_ENABLED` | `true` | 서버 리플렉션 노출 여부 |

### 전송 보안

인증서 체인과 개인키를 지정하면 모든 bind address가 TLS listener로 열립니다. 한쪽만 지정하면 평문으로 조용히 내려가지 않고 `IncompleteTlsCredentialsError`로 기동에 실패합니다.

```bash
export SPAKKY_GRPC_TLS_CERTIFICATE_CHAIN_FILE=/etc/tls/server.crt
export SPAKKY_GRPC_TLS_PRIVATE_KEY_FILE=/etc/tls/server.key
export SPAKKY_GRPC_TLS_CLIENT_CA_FILE=/etc/tls/ca.crt   # 상호 TLS
export SPAKKY_GRPC_REQUIRE_CLIENT_AUTH=true
```

`REQUIRE_CLIENT_AUTH`를 켰는데 CA 파일이 없으면 `MissingClientCertificateAuthorityError`로 실패합니다.

### 서버 옵션

keepalive, 최대 메시지 크기, 최대 연결 수명은 모두 `SERVER_OPTIONS` 한 곳에서 조정합니다. gRPC가 문서화한 채널 인자를 그대로 받습니다.

```bash
export SPAKKY_GRPC_SERVER_OPTIONS='{
  "grpc.keepalive_time_ms": 30000,
  "grpc.max_receive_message_length": 8388608,
  "grpc.max_connection_age_ms": 600000
}'
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

protobuf는 모든 method에 input/output 메시지 타입을 요구하므로 request 모델(첫 번째 인자)과 response 모델(반환 타입)을 모두 선언해야 합니다. 둘 중 하나라도 빠지면 컨트롤러 등록 시점에 `MessagelessRpcMethodError`가 발생하며, 에러의 `method_name`에 `컨트롤러명.메서드명`이 담깁니다.

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

**기본 동작 — 자동 번호 부여**: `ProtoField`를 생략하면 `DescriptorBuilder`가 필드 이름의 SHA-256 해시에서 protobuf 필드 번호를 자동으로 결정합니다. 이름에서 번호가 결정되므로 필드 선언 순서를 바꿔도 기존 번호는 변하지 않고, 필드를 추가해도 기존 번호가 보존되어 와이어 호환성이 유지됩니다. 단 새 필드 이름의 salt-0 해시가 기존 필드 번호와 충돌하는 드문 경우(약 5.4억분의 1 확률)에만 기존 필드가 재해싱되며, 이때는 `ProtoField(number=N)`으로 번호를 고정할 수 있습니다. 예약 구간 19000–19999는 자동으로 건너뜁니다.

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

`spakky-grpc` 플러그인이 제공하는 `GrpcServerSpec` Pod에 아래 세 PostProcessor가 순서대로 구성을 누적합니다. 실제 `grpc.aio.Server` 인스턴스는 `start()` 시점에 ApplicationContext의 이벤트 루프에서 `GrpcServerSpec.build_async()`로 생성됩니다.

| PostProcessor | Order | 역할 |
|--------------|-------|------|
| `RegisterServicesPostProcessor` | 0 | `@GrpcController`의 `@rpc` 메서드를 generic handler로 빌드하여 spec에 추가 |
| `AddInterceptorsPostProcessor` | 1 | `ErrorHandlingInterceptor`, `TracingInterceptor`를 spec에 추가 |
| `BindServerPostProcessor` | 2 | `GrpcServerService`를 ApplicationContext에 등록하여 spec 기반으로 서버를 생성·시작·종료 |

---

## 표준 서비스

애플리케이션 서비스와 함께 gRPC 생태계의 두 표준 서비스가 기본으로 열립니다.

| 서비스 | 설정 키 | 용도 |
|---|---|---|
| `grpc.health.v1.Health` | `SPAKKY_GRPC_HEALTH_SERVICE_ENABLED` | Kubernetes gRPC 네이티브 프로브 |
| `grpc.reflection.v1alpha.ServerReflection` | `SPAKKY_GRPC_REFLECTION_SERVICE_ENABLED` | 실행 중인 서버의 서비스·메시지 조회 |

두 서비스의 스키마도 플러그인의 `DescriptorRegistry`에 함께 등록되므로, 리플렉션이 목록에 올린 서비스는 모두 `describe`까지 가능합니다. `.proto` 산출물이 없는 code-first 서비스를 `grpcurl` 같은 도구로 진단할 때 이 경로가 유일한 수단입니다.

Kubernetes 프로브는 서비스 이름 없이 전체 상태를 조회하며, 기동 직후 `SERVING`입니다.

```yaml
livenessProbe:
  grpc:
    port: 50051
```

의존성이 끊겼을 때 특정 서비스를 `NOT_SERVING`으로 내리려면 헬스체크 servicer Pod를 주입합니다.

```python
from grpc_health.v1 import health, health_pb2


class OrderReadiness:
    def __init__(self, servicer: health.aio.HealthServicer) -> None:
        self.servicer = servicer

    async def mark_unavailable(self) -> None:
        await self.servicer.set(
            "example.echo.EchoController",
            health_pb2.HealthCheckResponse.NOT_SERVING,
        )
```

---

## 클라이언트 헬퍼

필드 번호가 필드 **이름**에서 도출되므로, 호출자가 메시지 모델을 따로 복제해 두면 이름을 바꾸는 리팩터링 한 번에 와이어가 갈라지고 필드가 조용히 사라집니다. `GrpcClient`는 서버가 등록하는 것과 같은 컨트롤러 클래스에서 descriptor를 만들고, 호출 대상도 문자열이 아니라 메서드 참조로 지정합니다.

```python
import grpc.aio
from spakky.plugins.grpc.client import GrpcClient

async with grpc.aio.insecure_channel("127.0.0.1:50051") as channel:
    client = GrpcClient(channel, EchoController)
    reply = await client.unary_unary(EchoController.echo)(EchoRequest(text="hello"))
```

| 메서드 | 대상 `RpcMethodType` | 반환 |
|---|---|---|
| `unary_unary` | `UNARY` | 응답 모델을 await |
| `unary_stream` | `SERVER_STREAMING` | 응답 모델을 async iterate |
| `stream_unary` | `CLIENT_STREAMING` | 요청 async iterator를 전달하고 응답을 await |
| `stream_stream` | `BIDI_STREAMING` | 요청 async iterator를 전달하고 응답을 async iterate |

선언과 다른 스트리밍 패턴을 요청하면 `RpcMethodTypeMismatchError`, `@rpc`가 없는 메서드를 넘기면 `NotAnRpcMethodError`로 호출 전에 실패합니다. 서버와 같은 프로세스에서 호출한다면 세 번째 인자로 서버의 `DescriptorRegistry`를 넘겨 descriptor 재컴파일을 생략할 수 있습니다.

---

## descriptor 스냅샷으로 와이어 파손 막기

필드 이름을 바꾸는 순간 필드 번호가 바뀌므로, `.proto` 산출물이 없는 code-first 방식에서는 편집기의 이름 바꾸기가 장애 원인이 됩니다. `spakky-grpc-descriptor-snapshot` 명령이 생성 결과(메시지 → 필드 이름 → 번호·타입)를 결정론적 JSON으로 출력하므로, 스냅샷을 커밋해 두고 CI에서 diff하면 이 변화를 배포 전에 잡을 수 있습니다.

```bash
spakky-grpc-descriptor-snapshot apps > descriptors.json
```

```bash
# CI 게이트: 와이어 배치가 바뀌면 실패
spakky-grpc-descriptor-snapshot apps | diff - descriptors.json
```

인자는 `@GrpcController`가 선언된 모듈 또는 패키지의 점 표기 경로이며, 패키지를 넘기면 하위 모듈까지 훑습니다. 명령은 실행 디렉터리를 `sys.path`에 추가하므로 프로젝트 루트에서 그대로 호출합니다.

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
| `ProtoFieldNumberConflictError` | 명시 `ProtoField` 번호가 자동 부여 필드의 번호와 충돌 |
| `MessagelessRpcMethodError` | `@rpc` 메서드가 request 또는 response 모델을 선언하지 않음 — 컨트롤러 등록 시점과 클라이언트 호출 생성 시점 모두에서 발생 |

### 전송 보안 설정 에러

| 에러 | 설명 |
|------|------|
| `IncompleteTlsCredentialsError` | 인증서 체인과 개인키 중 한쪽만 설정됨 |
| `MissingClientCertificateAuthorityError` | 클라이언트 인증을 요구했으나 client CA 파일이 없음 |

### 클라이언트 호출 에러

| 에러 | 설명 |
|------|------|
| `NotAnRpcMethodError` | `@rpc`가 없는 메서드로 호출을 만들려 함 |
| `RpcMethodTypeMismatchError` | 선언된 스트리밍 패턴과 다른 호출 형태를 요청 |

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

`SPAKKY_GRPC_BIND_ADDRESSES='["127.0.0.1:50051"]'`가 설정되어 있으면 `app.start()` 호출 시 PostProcessor 체인이 실행되어 `EchoController`의 핸들러와 인터셉터가 spec에 누적되고, `GrpcServerService`가 ApplicationContext의 이벤트 루프 스레드에서 `spec.build_async()`로 실제 서버를 생성한 뒤 `127.0.0.1:50051`에서 리슨합니다.

### 클라이언트 호출

클라이언트는 서버와 같은 컨트롤러 선언에서 `GrpcClient`를 만듭니다. 메시지 모델을 다시 정의하지 않으므로 필드 번호가 양쪽에서 갈라질 여지가 없습니다.

```python
# client.py
import asyncio

import grpc.aio

from spakky.plugins.grpc.client import GrpcClient

from apps.echo import EchoController, EchoRequest


async def main() -> None:
    async with grpc.aio.insecure_channel("127.0.0.1:50051") as channel:
        client = GrpcClient(channel, EchoController)
        reply = await client.unary_unary(EchoController.echo)(
            EchoRequest(text="hello")
        )
        print(reply.text)  # "hello"


asyncio.run(main())
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
