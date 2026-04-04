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
    ├── AbstractSpakkyFastAPIError (플러그인)
    ├── AbstractSpakkySqlAlchemyError (플러그인)
    ├── AbstractSpakkyOutboxError (플러그인)
    ├── AbstractSpakkyOpenTelemetryError (플러그인)
    └── ...
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

| 에러                           | 설명                            |
| ------------------------------ | ------------------------------- |
| `CannotDetermineScanPathError` | 스캔 경로를 자동 결정할 수 없음 |

#### AbstractSpakkyPodError

Pod 등록 및 인스턴스화 관련 에러입니다.

```python
from spakky.core.pod.error import AbstractSpakkyPodError
```

| 에러                                    | 설명                               |
| --------------------------------------- | ---------------------------------- |
| `PodAnnotationFailedError`              | Pod 어노테이션 처리 실패           |
| `PodInstantiationFailedError`           | Pod 인스턴스 생성 실패             |
| `CannotDeterminePodTypeError`           | Pod 타입 추론 불가                 |
| `CannotUseVarArgsInPodError`            | \*args/\*\*kwargs 사용 금지        |
| `CannotUsePositionalOnlyArgsInPodError` | 위치 전용 인자 사용 금지           |
| `CannotUseOptionalReturnTypeInPodError` | Optional 반환 타입 금지 (함수 Pod) |

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
```

| 에러                           | 설명                             |
| ------------------------------ | -------------------------------- |
| `AbstractSpakkySqlAlchemyError` | SQLAlchemy 에러 기반 클래스      |

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
