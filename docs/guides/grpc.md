# gRPC 통합

`spakky-grpc`는 code-first 방식의 gRPC 서비스 통합을 제공합니다. Python 타입에서 protobuf descriptor를 자동 생성하며, `@GrpcController`와 `@rpc` 데코레이터로 선언적으로 gRPC 서비스를 정의합니다.

---

## 동작 원리

1. `@GrpcController`로 gRPC 서비스 컨트롤러를 선언
2. `@rpc`로 메서드를 RPC 엔드포인트로 마크
3. `ProtoField` 어노테이션으로 요청/응답 타입에 protobuf 메타데이터 부착
4. `DescriptorBuilder`가 Python 타입에서 protobuf descriptor를 자동 생성
5. PostProcessor들이 서비스 등록, 인터셉터 추가, 서버 바인딩을 자동 처리

---

## 설정

```bash
pip install spakky-grpc
```

`spakky-grpc`는 `spakky`, `spakky-tracing`, `grpcio`에 의존합니다.

```python
import spakky.plugins.grpc

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

dataclass 필드에 protobuf 필드 번호를 부착합니다. `.proto` 파일 없이 Python 타입만으로 protobuf descriptor를 생성합니다.

```python
from typing import Annotated
from spakky.core.common.mutability import immutable
from spakky.plugins.grpc.annotations.field import ProtoField

@immutable
class GetUserRequest:
    user_id: Annotated[str, ProtoField(number=1)]

@immutable
class GetUserResponse:
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

### DescriptorRegistry

protobuf descriptor를 캐싱하고 관리합니다. `DescriptorBuilder`가 `ProtoField` 어노테이션이 부착된 Python 타입에서 descriptor를 자동 생성합니다.

---

## 인터셉터

### TracingInterceptor

`spakky-tracing`과 연동하여 gRPC 요청의 분산 트레이싱을 자동 처리합니다. 요청 메타데이터에서 `traceparent` 헤더를 추출하여 `TraceContext`를 복원합니다.

### ErrorHandlingInterceptor

`AbstractGrpcStatusError` 서브클래스를 적절한 gRPC 상태 코드로 자동 변환합니다. 처리되지 않은 예외는 `INTERNAL` 상태로 매핑됩니다.

---

## PostProcessor

| PostProcessor | 역할 |
|--------------|------|
| `RegisterServicesPostProcessor` | `@GrpcController`의 `@rpc` 메서드를 gRPC 서비스로 등록 |
| `AddInterceptorsPostProcessor` | `TracingInterceptor`, `ErrorHandlingInterceptor` 자동 추가 |
| `BindServerPostProcessor` | gRPC 서버 바인딩 및 라이프사이클 관리 |

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
| `MissingProtoFieldAnnotationError` | `ProtoField` 어노테이션 누락 |
| `DescriptorAlreadyRegisteredError` | 이미 등록된 descriptor 재등록 시도 |

---

## 다음 단계

- [DI & Pod](dependency-injection.md) — 의존성 주입 기본
- [분산 트레이싱](tracing.md) — TraceContext, Propagator
- [FastAPI 통합](fastapi.md) — REST 컨트롤러 (비교)
