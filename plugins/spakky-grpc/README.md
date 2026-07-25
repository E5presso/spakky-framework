# spakky-grpc

> [Spakky Framework](https://framework.spakky.com)를 위한 code-first gRPC 플러그인입니다.
> `@GrpcController`와 `@rpc` 선언을 gRPC service descriptor와 server binding으로 자동 변환합니다.

pydantic `BaseModel`로 메시지를 선언하고 `@GrpcController` + `@rpc` 데코레이터로 서비스를 정의하면, 런타임에 protobuf descriptor를 자동 생성하여 `grpc.aio.Server`에 등록합니다. `.proto` 파일이나 codegen 단계가 필요 없습니다. protobuf ↔ BaseModel 변환은 `google.protobuf.json_format` 브릿지(JSON 중간 표현)로 수행됩니다.

## 설치

```bash
pip install spakky-grpc
```

의존성: `grpcio`, `grpcio-health-checking`, `grpcio-reflection`, `protobuf`, `pydantic>=2.4`, `pydantic-settings`, `spakky`, `spakky-auth`, `spakky-tracing`.

## 빠른 시작

```bash
export SPAKKY_GRPC_BIND_ADDRESSES='["127.0.0.1:50051"]'
```

```python
from pydantic import BaseModel
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

import spakky.plugins.grpc
from spakky.plugins.grpc.decorators.rpc import rpc
from spakky.plugins.grpc.stereotypes.grpc_controller import GrpcController

import apps  # `@GrpcController`-decorated classes live in your own package


# ProtoField 없이 — 필드 번호는 필드 이름 해시로 자동 결정됩니다.
class HelloRequest(BaseModel):
    name: str


class HelloReply(BaseModel):
    message: str


@GrpcController(package="example.hello")
class HelloController:
    @rpc()
    async def say_hello(self, request: HelloRequest) -> HelloReply:
        return HelloReply(message=f"Hello, {request.name}!")


app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins(include={spakky.plugins.grpc.PLUGIN_NAME})
    .scan(apps)  # your package containing HelloController above
)
app.start()  # 서버가 별도 이벤트 루프 스레드에서 구동됩니다
```

플러그인은 `GrpcConfig`, `GrpcServerSpec`, `DescriptorRegistry`, 그리고 헬스체크 servicer를 기본 Pod로 등록합니다. `GrpcServerSpec`는 핸들러·인터셉터·바인드 대상·채널 옵션·표준 서비스 등록 콜백을 누적합니다. 실제 `grpc.aio.Server`는 `ApplicationContext`의 이벤트 루프 스레드에서 `spec.build_async()`로 생성되므로 `grpc.aio` 내부 Future가 올바른 루프에 바인딩됩니다. `SPAKKY_GRPC_BIND_ADDRESSES`가 비어 있으면 listener를 열지 않습니다.

## 설정

모든 값은 `SPAKKY_GRPC_` 접두사 환경변수로 주입합니다.

| 환경변수 | 타입 | 기본값 | 역할 |
|---|---|---|---|
| `SPAKKY_GRPC_BIND_ADDRESSES` | `tuple[str, ...]` | `()` | listener 주소 목록 (`host:port`) |
| `SPAKKY_GRPC_SERVER_OPTIONS` | `dict[str, int \| str]` | `{}` | `grpc.aio.server(options=...)`로 그대로 전달되는 채널 인자 |
| `SPAKKY_GRPC_TLS_CERTIFICATE_CHAIN_FILE` | `Path \| None` | `None` | 서버 인증서 체인 PEM 파일 |
| `SPAKKY_GRPC_TLS_PRIVATE_KEY_FILE` | `Path \| None` | `None` | 인증서 체인에 대응하는 개인키 PEM 파일 |
| `SPAKKY_GRPC_TLS_CLIENT_CA_FILE` | `Path \| None` | `None` | 클라이언트 인증서를 서명한 CA PEM 파일 (mTLS) |
| `SPAKKY_GRPC_REQUIRE_CLIENT_AUTH` | `bool` | `false` | 클라이언트 인증서 제시 강제 여부 |
| `SPAKKY_GRPC_HEALTH_SERVICE_ENABLED` | `bool` | `true` | `grpc.health.v1.Health` 서비스 노출 여부 |
| `SPAKKY_GRPC_REFLECTION_SERVICE_ENABLED` | `bool` | `true` | 서버 리플렉션 서비스 노출 여부 |

### 전송 보안 (TLS·mTLS)

인증서 체인과 개인키를 지정하면 `BIND_ADDRESSES`의 모든 주소가 `add_secure_port`로 바인딩됩니다. 둘 중 하나만 지정하면 평문으로 조용히 내려가지 않고 `IncompleteTlsCredentialsError`로 기동에 실패합니다.

```bash
export SPAKKY_GRPC_BIND_ADDRESSES='["0.0.0.0:50051"]'
export SPAKKY_GRPC_TLS_CERTIFICATE_CHAIN_FILE=/etc/tls/server.crt
export SPAKKY_GRPC_TLS_PRIVATE_KEY_FILE=/etc/tls/server.key
# 상호 TLS까지 요구할 때
export SPAKKY_GRPC_TLS_CLIENT_CA_FILE=/etc/tls/ca.crt
export SPAKKY_GRPC_REQUIRE_CLIENT_AUTH=true
```

`REQUIRE_CLIENT_AUTH=true`인데 CA 파일이 없으면 `MissingClientCertificateAuthorityError`로 실패합니다 — 검증할 신뢰 기관이 없는 상태로 mTLS를 켠 것으로 간주합니다.

### 서버 옵션

`SERVER_OPTIONS`는 gRPC 채널 인자를 그대로 받습니다. 플러그인이 개별 항목을 열거하지 않으므로 keepalive·최대 메시지 크기·최대 연결 수명을 모두 이 한 곳에서 조정합니다.

```bash
export SPAKKY_GRPC_SERVER_OPTIONS='{
  "grpc.keepalive_time_ms": 30000,
  "grpc.max_receive_message_length": 8388608,
  "grpc.max_connection_age_ms": 600000
}'
```

## 표준 서비스

| 서비스 | 설정 키 | 용도 |
|---|---|---|
| `grpc.health.v1.Health` | `HEALTH_SERVICE_ENABLED` | Kubernetes gRPC 네이티브 프로브 |
| `grpc.reflection.v1alpha.ServerReflection` | `REFLECTION_SERVICE_ENABLED` | 실행 중인 서버의 서비스·메시지 조회 |

두 서비스의 스키마는 플러그인 자체 `DescriptorRegistry`에 함께 등록되므로, 리플렉션이 목록에 올린 서비스는 모두 `describe`도 가능합니다.

헬스 상태를 직접 조작하려면 `grpc_health_servicer` Pod를 주입합니다.

```python
from grpc_health.v1 import health, health_pb2


class DatabaseProbe:
    def __init__(self, servicer: health.aio.HealthServicer) -> None:
        self.servicer = servicer

    async def mark_unavailable(self) -> None:
        await self.servicer.set(
            "example.hello.HelloController",
            health_pb2.HealthCheckResponse.NOT_SERVING,
        )
```

## 클라이언트 헬퍼

필드 번호가 필드 **이름**에서 도출되므로, 호출자가 메시지 모델을 따로 베껴 두면 이름 한 글자 차이로 와이어가 갈라집니다. `GrpcClient`는 서버가 등록하는 것과 같은 컨트롤러 클래스에서 descriptor를 만들고, 호출할 메서드도 문자열이 아니라 **메서드 참조**로 지정합니다.

```python
import grpc.aio
from spakky.plugins.grpc.client import GrpcClient

channel = grpc.aio.insecure_channel("127.0.0.1:50051")
client = GrpcClient(channel, HelloController)

reply = await client.unary_unary(HelloController.say_hello)(HelloRequest(name="spakky"))
```

| 메서드 | 대상 `RpcMethodType` |
|---|---|
| `unary_unary` | `UNARY` |
| `unary_stream` | `SERVER_STREAMING` |
| `stream_unary` | `CLIENT_STREAMING` |
| `stream_stream` | `BIDI_STREAMING` |

선언과 다른 패턴을 요청하면 호출 전에 `RpcMethodTypeMismatchError`, `@rpc`가 없는 메서드를 넘기면 `NotAnRpcMethodError`로 실패합니다. 서버와 같은 프로세스에서 호출한다면 `registry` 인자로 서버의 `DescriptorRegistry`를 공유해 descriptor 재컴파일을 생략할 수 있습니다.

## descriptor 스냅샷 명령

`spakky-grpc-descriptor-snapshot` 명령은 컨트롤러에서 생성되는 와이어 배치(메시지 → 필드 이름 → 번호·타입)를 결정론적 JSON으로 출력합니다. 스냅샷을 저장소에 커밋해 두면 필드 이름 변경 같은 와이어 파손을 CI에서 diff로 잡을 수 있습니다.

```bash
spakky-grpc-descriptor-snapshot apps > descriptors.json
# CI 게이트
spakky-grpc-descriptor-snapshot apps | diff - descriptors.json
```

인자는 `@GrpcController`가 선언된 모듈 또는 패키지의 점 표기 경로입니다. 패키지를 넘기면 하위 모듈까지 훑습니다. 명령은 실행 디렉터리를 `sys.path`에 추가하므로 프로젝트 루트에서 그대로 호출합니다.

## 타입 매핑

pydantic `BaseModel`의 각 필드를 protobuf 필드로 매핑합니다. `ProtoField` 어노테이션은 선택 사항입니다.

### 필드 번호 할당

필드 번호는 다음 규칙으로 결정됩니다.

- **자동 도출 (기본)**: `ProtoField` 어노테이션이 없으면 필드 이름의 SHA-256 해시로부터 번호를 결정합니다. 번호는 유효 범위 `1`..`536_870_911` 안에 들어오며, protobuf가 예약한 `19_000`..`19_999` 구간을 피합니다. 필드 **순서 변경**은 번호를 절대 바꾸지 않습니다(할당이 이름 집합의 순수 함수). 필드 **추가** 역시 기존 번호를 보존하지만, 새 필드 이름의 salt-0 해시가 기존 필드가 차지한 번호와 충돌하는 드문 경우(약 5.4억분의 1 확률)에 한해 기존 필드가 재해싱됩니다. 특정 필드의 번호를 무조건 고정해야 하면 `ProtoField(number=N)`으로 명시 지정하세요.
- **명시 지정 (오버라이드)**: `Annotated[T, ProtoField(number=N)]`을 붙이면 해당 필드는 `N`번을 사용합니다. 동일 메시지 안에서 자동 도출 필드와 혼용할 수 있습니다.

```python
from pydantic import BaseModel
from typing import Annotated
from spakky.plugins.grpc.annotations.field import ProtoField

# ProtoField 없이 — 번호는 필드 이름 해시로 자동 결정
class HelloRequest(BaseModel):
    name: str

# ProtoField로 번호 명시 지정
class HelloReply(BaseModel):
    message: Annotated[str, ProtoField(number=1)]
```

### 타입 매핑 표

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
| 2 | `BindServerPostProcessor` | `GrpcServerService`를 `ApplicationContext`에 등록 (start_async에서 `spec.build_async()`) |

## 개발 검증

패키지 단위 검증은 해당 패키지 디렉토리에서 실행합니다.

```bash
uv run ruff format .
uv run ruff check .
uv run pyrefly check
uv run pytest
```

`pytest`는 각 패키지 `pyproject.toml`의 coverage 설정을 사용합니다.

## 라이선스

MIT License입니다. [Spakky Framework repository](https://github.com/E5presso/spakky-framework)를 참고하세요.
