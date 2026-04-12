# 에러 계층 구조

이 문서는 Spakky Framework의 에러 클래스 계층 구조와 사용법을 설명합니다.

---

## 개요

Spakky는 구조화된 에러 계층을 제공합니다. 모든 프레임워크 에러는 `AbstractSpakkyFrameworkError`를 상속하며, 각 패키지별로 전용 기반 에러 클래스가 있습니다.

```
Exception
└── AbstractSpakkyFrameworkError
    ├── AbstractSpakkyApplicationError
    ├── AbstractSpakkyAOPError
    ├── AbstractSpakkyPodError
    ├── AbstractSpakkyDomainError
    │   ├── AbstractDomainValidationError
    │   ├── EntityNotFoundError
    │   └── VersionConflictError
    ├── AbstractSpakkyPersistencyError
    ├── AbstractSpakkyExternalError
    ├── AbstractSpakkyEventError
    ├── AbstractSpakkyTaskError
    ├── AbstractSpakkyTracingError
    ├── AbstractSpakkyOutboxError
    ├── AbstractSpakkySagaError
    │   ├── SagaFlowDefinitionError
    │   ├── SagaCompensationFailedError
    │   ├── SagaStepTimeoutError
    │   ├── SagaParallelMergeConflictError
    │   └── SagaEngineNotConnectedError
    ├── AbstractSpakkyFastAPIError (플러그인)
    ├── AbstractSpakkySqlAlchemyError (플러그인)
    │   ├── AbstractSpakkySqlAlchemyORMError
    │   └── AbstractSpakkySqlAlchemyPersistencyError
    ├── AbstractSpakkyCeleryError (플러그인)
    ├── AbstractSpakkyOpenTelemetryError (플러그인)
    ├── AbstractSpakkyGrpcError (플러그인)
    │   ├── AbstractGrpcStatusError
    │   │   ├── InvalidArgument
    │   │   ├── NotFound
    │   │   ├── AlreadyExists
    │   │   ├── PermissionDenied
    │   │   ├── Unauthenticated
    │   │   ├── FailedPrecondition
    │   │   ├── Unavailable
    │   │   └── InternalError
    │   ├── UnsupportedFieldTypeError
    │   ├── MissingProtoFieldAnnotationError
    │   └── DescriptorAlreadyRegisteredError
    ├── DecryptionFailedError (spakky-security)
    ├── KeySizeError (spakky-security)
    ├── PrivateKeyRequiredError (spakky-security)
    ├── CannotImportAsymmetricKeyError (spakky-security)
    ├── InvalidJWTFormatError (spakky-security)
    ├── JWTDecodingError (spakky-security)
    └── JWTProcessingError (spakky-security)
```

---

## 기반 에러 클래스

### AbstractSpakkyFrameworkError

모든 Spakky 프레임워크 에러의 최상위 기반 클래스입니다.

```python
from spakky.core.common.error import AbstractSpakkyFrameworkError

class AbstractSpakkyFrameworkError(Exception, ABC):
    """모든 Spakky 프레임워크 에러의 기반 클래스"""

    message: ClassVar[str]  # 에러 메시지 (클래스 수준 또는 인스턴스 수준)
```

**특징:**

- `message` 속성으로 사람이 읽을 수 있는 에러 메시지 제공
- 클래스 수준 기본 메시지 또는 인스턴스별 커스텀 메시지 지원

---

## 코어 패키지 에러

### spakky (코어)

#### AbstractSpakkyApplicationError

애플리케이션 부트스트랩 관련 에러입니다.

```python
from spakky.core.application.error import AbstractSpakkyApplicationError
```

| 에러                                                    | 설명                                  |
| ------------------------------------------------------- | ------------------------------------- |
| `CannotDetermineScanPathError`                          | 스캔 경로를 자동 결정할 수 없음       |
| `ApplicationContextAlreadyStartedError`                 | 이미 시작된 컨텍스트를 재시작 시도    |
| `ApplicationContextAlreadyStoppedError`                 | 이미 중지된 컨텍스트를 재중지 시도    |
| `EventLoopThreadNotStartedInApplicationContextError`    | 이벤트 루프 스레드 미시작 상태에서 접근 |
| `EventLoopThreadAlreadyStartedInApplicationContextError`| 이벤트 루프 스레드 중복 시작 시도     |

#### AbstractSpakkyPodError

Pod 등록 및 인스턴스화 관련 에러입니다.

```python
from spakky.core.pod.error import AbstractSpakkyPodError
```

| 에러                                      | 설명                               |
| ----------------------------------------- | ---------------------------------- |
| `PodAnnotationFailedError`                | Pod 어노테이션 처리 실패           |
| `PodInstantiationFailedError`             | Pod 인스턴스 생성 실패             |
| `CannotDeterminePodTypeError`             | Pod 타입 추론 불가                 |
| `CannotUseVarArgsInPodError`              | \*args/\*\*kwargs 사용 금지        |
| `CannotUsePositionalOnlyArgsInPodError`   | 위치 전용 인자 사용 금지           |
| `CannotUseOptionalReturnTypeInPodError`   | Optional 반환 타입 금지 (함수 Pod) |
| `UnexpectedDependencyNameInjectedError`   | 예상치 못한 이름의 의존성 주입     |
| `UnexpectedDependencyTypeInjectedError`   | 예상치 못한 타입의 의존성 주입     |

#### 컨테이너 에러

```python
from spakky.core.pod.interfaces.container import (
    CircularDependencyGraphDetectedError,
    NoSuchPodError,
    NoUniquePodError,
    CannotRegisterNonPodObjectError,
    PodNameAlreadyExistsError,
)
```

| 에러                                   | 설명                       |
| -------------------------------------- | -------------------------- |
| `CircularDependencyGraphDetectedError` | 순환 의존성 감지           |
| `NoSuchPodError`                       | 요청한 Pod를 찾을 수 없음  |
| `NoUniquePodError`                     | 여러 후보 Pod 중 선택 불가 |
| `CannotRegisterNonPodObjectError`      | @Pod 없는 객체 등록 시도   |
| `PodNameAlreadyExistsError`            | Pod 이름 중복              |

#### AbstractSpakkyAOPError

AOP 관련 에러입니다.

```python
from spakky.core.aop.error import AbstractSpakkyAOPError
```

| 에러                     | 설명                                 |
| ------------------------ | ------------------------------------ |
| `AspectInheritanceError` | Aspect가 IAspect/IAsyncAspect 미구현 |

---

### spakky-domain

도메인 모델 관련 에러입니다.

```python
from spakky.domain.error import (
    AbstractSpakkyDomainError,
    AbstractDomainValidationError,
)
```

| 에러                            | 설명                         |
| ------------------------------- | ---------------------------- |
| `AbstractSpakkyDomainError`     | 도메인 에러 기반 클래스      |
| `AbstractDomainValidationError` | 도메인 검증 에러 기반 클래스 |
| `CannotMonkeyPatchEntityError`  | Entity 속성 직접 변경 시도   |

---

### spakky-event

이벤트 시스템 관련 에러입니다.

```python
from spakky.event.error import (
    AbstractSpakkyEventError,
    InvalidMessageError,
)
```

| 에러                  | 설명               |
| --------------------- | ------------------ |
| `InvalidMessageError` | 잘못된 메시지 형식 |

---

### spakky-data

데이터 접근 관련 에러입니다.

```python
from spakky.data.persistency.error import AbstractSpakkyPersistencyError
from spakky.data.persistency.repository import EntityNotFoundError, VersionConflictError
from spakky.data.external.error import AbstractSpakkyExternalError
```

| 에러                            | 설명                           | 상속                          |
| ------------------------------- | ------------------------------ | ----------------------------- |
| `AbstractSpakkyPersistencyError` | 영속성 에러 기반 클래스        | `AbstractSpakkyFrameworkError` |
| `EntityNotFoundError`           | 엔티티 조회 실패               | `AbstractSpakkyDomainError`   |
| `VersionConflictError`          | 낙관적 락 충돌                 | `AbstractSpakkyDomainError`   |
| `AbstractSpakkyExternalError`   | 외부 서비스 에러 기반 클래스   | `AbstractSpakkyFrameworkError` |

---

### spakky-task

태스크 시스템 관련 에러입니다.

```python
from spakky.task.error import (
    AbstractSpakkyTaskError,
    TaskNotFoundError,
    DuplicateTaskError,
    InvalidScheduleSpecificationError,
)
```

| 에러                                | 설명                                                    |
| ----------------------------------- | ------------------------------------------------------- |
| `TaskNotFoundError`                 | 레지스트리에서 태스크를 찾을 수 없음                    |
| `DuplicateTaskError`               | 중복 태스크 등록 시도                                   |
| `InvalidScheduleSpecificationError` | `@schedule`에 `interval`/`at`/`crontab` 중 하나만 필요 |

---

### spakky-tracing

분산 트레이싱 관련 에러입니다.

```python
from spakky.tracing.error import (
    AbstractSpakkyTracingError,
    InvalidTraceparentError,
)
```

| 에러                      | 설명                               |
| ------------------------- | ---------------------------------- |
| `InvalidTraceparentError` | `traceparent` 헤더 형식이 유효하지 않음 |

---

## 플러그인 에러

### spakky-fastapi

FastAPI 통합 관련 에러입니다. HTTP 상태 코드와 JSON 응답 변환을 지원합니다.

```python
from spakky.plugins.fastapi.error import (
    AbstractSpakkyFastAPIError,
    BadRequest,
    Unauthorized,
    Forbidden,
    NotFound,
    Conflict,
    InternalServerError,
)
```

| 에러                  | HTTP 상태 | 설명           |
| --------------------- | --------- | -------------- |
| `BadRequest`          | 400       | 잘못된 요청    |
| `Unauthorized`        | 401       | 인증 필요      |
| `Forbidden`           | 403       | 접근 권한 없음 |
| `NotFound`            | 404       | 리소스 없음    |
| `Conflict`            | 409       | 리소스 충돌    |
| `InternalServerError` | 500       | 내부 서버 에러 |

**JSON 응답 변환:**

```python
from spakky.plugins.fastapi.error import NotFound

try:
    user = await repository.find_by_id(user_id)
    if user is None:
        raise NotFound()
except NotFound as e:
    return e.to_response(show_traceback=False)
```

응답 예시:

```json
{
	"message": "Not Found",
	"args": [],
	"traceback": null
}
```

### spakky-sqlalchemy

SQLAlchemy 통합 관련 에러입니다.

```python
from spakky.plugins.sqlalchemy.error import AbstractSpakkySqlAlchemyError
from spakky.plugins.sqlalchemy.orm.error import AbstractSpakkySqlAlchemyORMError
from spakky.plugins.sqlalchemy.persistency.error import AbstractSpakkySqlAlchemyPersistencyError
```

| 에러                                      | 설명                             | 상속                           |
| ----------------------------------------- | -------------------------------- | ------------------------------ |
| `AbstractSpakkySqlAlchemyError`           | SQLAlchemy 에러 기반 클래스      | `AbstractSpakkyFrameworkError` |
| `AbstractSpakkySqlAlchemyORMError`        | ORM 에러 기반 클래스             | `AbstractSpakkySqlAlchemyError` |
| `AbstractSpakkySqlAlchemyPersistencyError`| 영속성 에러 기반 클래스          | `AbstractSpakkySqlAlchemyError` |
| `CannotUseTableAnnotationError`           | @Table 데코레이터 사용 오류      | `AbstractSpakkySqlAlchemyORMError` |
| `TargetDomainNotSpecifiedError`           | @Table에 도메인 타입 미지정      | `AbstractSpakkySqlAlchemyORMError` |
| `NoSchemaFoundFromDomainError`            | 도메인 타입에 대한 스키마 없음   | `AbstractSpakkySqlAlchemyORMError` |
| `CannotDetermineAggregateTypeError`       | Aggregate 타입 추론 불가         | `AbstractSpakkySqlAlchemyPersistencyError` |
| `SessionNotInitializedError`              | 세션 미초기화 상태에서 접근      | `AbstractSpakkySqlAlchemyPersistencyError` |

### spakky-celery

Celery 통합 관련 에러입니다.

```python
from spakky.plugins.celery.error import (
    AbstractSpakkyCeleryError,
    InvalidScheduleRouteError,
)
```

| 에러                          | 설명                                          |
| ----------------------------- | --------------------------------------------- |
| `AbstractSpakkyCeleryError`   | Celery 에러 기반 클래스                        |
| `InvalidScheduleRouteError`   | ScheduleRoute에 유효한 스케줄 명세가 없음      |

### spakky-security

보안 관련 에러입니다. `spakky-security` 에러들은 패키지별 기반 클래스 없이 `AbstractSpakkyFrameworkError`를 직접 상속합니다.

```python
from spakky.plugins.security.error import (
    DecryptionFailedError,
    KeySizeError,
    PrivateKeyRequiredError,
    CannotImportAsymmetricKeyError,
    InvalidJWTFormatError,
    JWTDecodingError,
    JWTProcessingError,
)
```

| 에러                              | 설명                              |
| --------------------------------- | --------------------------------- |
| `DecryptionFailedError`          | 복호화 실패 (키 오류 또는 데이터 손상) |
| `KeySizeError`                   | 유효하지 않은 암호화 키 크기       |
| `PrivateKeyRequiredError`        | 비대칭 키 연산 시 개인키 미제공    |
| `CannotImportAsymmetricKeyError` | 비대칭 키 임포트 실패              |
| `InvalidJWTFormatError`          | JWT 토큰 형식 오류                 |
| `JWTDecodingError`               | JWT 토큰 디코딩 실패              |
| `JWTProcessingError`             | JWT 토큰 처리 중 오류             |

### spakky-outbox

Transactional Outbox 관련 에러입니다.

```python
from spakky.outbox.error import AbstractSpakkyOutboxError
```

| 에러                        | 설명                        |
| --------------------------- | --------------------------- |
| `AbstractSpakkyOutboxError` | Outbox 에러 기반 클래스     |

### spakky-opentelemetry

OpenTelemetry 통합 관련 에러입니다.

```python
from spakky.plugins.opentelemetry.error import (
    AbstractSpakkyOpenTelemetryError,
    UnsupportedExporterTypeError,
)
```

| 에러                              | 설명                                    |
| --------------------------------- | --------------------------------------- |
| `AbstractSpakkyOpenTelemetryError` | OpenTelemetry 에러 기반 클래스          |
| `UnsupportedExporterTypeError`    | 지원하지 않는 exporter 타입 설정 시 발생 |

### spakky-saga

사가 오케스트레이션 관련 에러입니다.

```python
from spakky.saga.error import (
    AbstractSpakkySagaError,
    SagaFlowDefinitionError,
    SagaCompensationFailedError,
    SagaStepTimeoutError,
    SagaParallelMergeConflictError,
    SagaEngineNotConnectedError,
)
```

| 에러                                | 설명                                          |
| ----------------------------------- | --------------------------------------------- |
| `AbstractSpakkySagaError`           | 사가 에러 기반 클래스                       |
| `SagaFlowDefinitionError`          | SagaFlow 정의 오류 (잘못된 흐름 구성)        |
| `SagaCompensationFailedError`       | 보상 로직 실행 중 예외 발생                |
| `SagaStepTimeoutError`              | step 타임아웃 초과 (엔진 내부, `on_error` 전략으로 라우팅) |
| `SagaParallelMergeConflictError`    | 병렬 단계 결과 병합 시 충돌                 |
| `SagaEngineNotConnectedError`       | 사가 엔진이 초기화되지 않은 상태에서 실행 시도 |

### spakky-grpc

gRPC 통합 관련 에러입니다. gRPC 상태 코드 매핑 에러와 스키마 에러로 나늉니다.

```python
from spakky.plugins.grpc.error import (
    AbstractSpakkyGrpcError,
    AbstractGrpcStatusError,
    InvalidArgument,
    NotFound,
    AlreadyExists,
    PermissionDenied,
    Unauthenticated,
    FailedPrecondition,
    Unavailable,
    InternalError,
    UnsupportedFieldTypeError,
    MissingProtoFieldAnnotationError,
    DescriptorAlreadyRegisteredError,
)
```

**gRPC 상태 코드 에러:**

| 에러                  | gRPC 상태 코드        | 설명                |
| --------------------- | ---------------------- | ------------------- |
| `InvalidArgument`     | `INVALID_ARGUMENT`     | 잘못된 요청 인자       |
| `NotFound`            | `NOT_FOUND`            | 리소스 없음           |
| `AlreadyExists`       | `ALREADY_EXISTS`       | 리소스 이미 존재       |
| `PermissionDenied`    | `PERMISSION_DENIED`    | 권한 없음              |
| `Unauthenticated`     | `UNAUTHENTICATED`      | 인증 필요              |
| `FailedPrecondition`  | `FAILED_PRECONDITION`  | 사전 조건 미충족       |
| `Unavailable`         | `UNAVAILABLE`          | 서비스 이용 불가        |
| `InternalError`       | `INTERNAL`             | 내부 서버 에러          |

**스키마 에러:**

| 에러                                  | 설명                                       |
| ------------------------------------- | ------------------------------------------ |
| `UnsupportedFieldTypeError`           | 지원하지 않는 protobuf 필드 타입          |
| `MissingProtoFieldAnnotationError`    | `ProtoField` 어노테이션 누락              |
| `DescriptorAlreadyRegisteredError`    | 이미 등록된 descriptor 재등록 시도     |

---

## 커스텀 에러 정의

### 도메인 에러

```python
from spakky.domain.error import AbstractDomainValidationError

class InvalidEmailError(AbstractDomainValidationError):
    """잘못된 이메일 형식"""
    message = "Invalid email format"

class InsufficientBalanceError(AbstractDomainValidationError):
    """잔액 부족"""
    message = "Insufficient balance for this operation"
```

### 애플리케이션 에러

```python
from spakky.core.application.error import AbstractSpakkyApplicationError

class ConfigurationError(AbstractSpakkyApplicationError):
    """설정 오류"""
    message = "Invalid configuration"
```

### HTTP 에러 (FastAPI)

```python
from spakky.plugins.fastapi.error import AbstractSpakkyFastAPIError
from typing import ClassVar
from fastapi import status

class TooManyRequestsError(AbstractSpakkyFastAPIError):
    """요청 제한 초과"""
    message = "Too many requests"
    status_code: ClassVar[int] = status.HTTP_429_TOO_MANY_REQUESTS
```

---

## 에러 처리 패턴

### try-except로 특정 에러 처리

```python
from spakky.core.pod.interfaces.container import NoSuchPodError, NoUniquePodError

try:
    service = context.get(IUserService)
except NoSuchPodError:
    logger.error("UserService not registered")
    raise
except NoUniquePodError:
    logger.error("Multiple UserService candidates")
    raise
```

### 에러 계층으로 그룹 처리

```python
from spakky.domain.error import AbstractDomainValidationError

try:
    user = User.create(command)
except AbstractDomainValidationError as e:
    # 모든 도메인 검증 에러를 한번에 처리
    return {"error": e.message}
```

### FastAPI 에러 핸들러

```python
from fastapi import FastAPI
from spakky.plugins.fastapi.error import AbstractSpakkyFastAPIError

app = FastAPI()

@app.exception_handler(AbstractSpakkyFastAPIError)
async def handle_spakky_error(request, exc: AbstractSpakkyFastAPIError):
    return exc.to_response(show_traceback=app.debug)
```

---

## 모범 사례

### 1. 적절한 기반 클래스 선택

```python
# 도메인 로직 에러 → AbstractDomainValidationError
class InvalidOrderStateError(AbstractDomainValidationError):
    message = "Cannot cancel a shipped order"

# HTTP 응답 에러 → AbstractSpakkyFastAPIError
class OrderNotFoundError(NotFound):
    message = "Order not found"
```

### 2. 상세 메시지 제공

```python
class CircularDependencyGraphDetectedError(AbstractSpakkyPodError):
    message = "Circular dependency graph detected"

    def __init__(self, dependency_chain: list[type]) -> None:
        super().__init__()
        self.dependency_chain = dependency_chain

    def __str__(self) -> str:
        # 상세한 의존성 경로 표시
        return f"{self.message}\nPath: {' -> '.join(t.__name__ for t in self.dependency_chain)}"
```

### 3. 에러 체이닝

```python
try:
    result = external_service.call()
except ExternalError as e:
    raise ApplicationError("External service failed") from e
```

### 4. 로깅과 함께 사용

```python
import logging

logger = logging.getLogger(__name__)

try:
    pod = context.get(IService)
except NoSuchPodError as e:
    logger.error(f"Service not found: {e}", exc_info=True)
    raise
```

---

## 에러 테스트

```python
import pytest
from spakky.domain.error import AbstractDomainValidationError

class InvalidEmailError(AbstractDomainValidationError):
    message = "Invalid email"

def test_invalid_email_error():
    with pytest.raises(InvalidEmailError) as exc_info:
        raise InvalidEmailError()

    assert exc_info.value.message == "Invalid email"
    assert isinstance(exc_info.value, AbstractDomainValidationError)

def test_error_hierarchy():
    error = InvalidEmailError()

    # 계층 확인
    assert isinstance(error, AbstractDomainValidationError)
    assert isinstance(error, Exception)
```
