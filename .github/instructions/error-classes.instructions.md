---
applyTo: "**/error.py"
---

# 에러 클래스 규칙

이 규칙은 모든 `error.py` 파일에 자동 적용됩니다.

## 계층 구조

모든 프레임워크 에러는 `AbstractSpakkyFrameworkError`를 상속합니다.
각 도메인별 추상 베이스 클래스를 거쳐 구체 에러를 정의합니다.

```
AbstractSpakkyFrameworkError (ABC)
├── AbstractSpakky<Domain>Error (ABC)
│   └── Concrete<Purpose>Error
```

## 단순 에러 (추가 컨텍스트 불필요)

`message` 클래스 속성만 정의합니다. `__init__`을 오버라이드하지 마세요.

```python
class CannotUseOptionalReturnTypeInPodError(PodAnnotationFailedError):
    """Raised when function Pod has Optional return type."""

    message = "Cannot use optional return type in pod"
```

## 구조화된 에러 (컨텍스트 데이터 필요)

`__init__`을 오버라이드하여 구조화된 데이터를 저장합니다.
**`__str__`을 오버라이드하지 마세요** — 상세 메시지는 로그에서 처리합니다.

```python
class CircularDependencyGraphDetectedError(AbstractSpakkyPodError):
    """Raised when circular dependency is detected."""

    message = "Circular dependency graph detected"

    def __init__(self, dependency_chain: list[type]) -> None:
        super().__init__()
        self.dependency_chain = dependency_chain

# 로깅 (상세 메시지는 여기서):
except CircularDependencyGraphDetectedError as e:
    logger.error(
        "Circular dependency detected: %s",
        " -> ".join(t.__name__ for t in e.dependency_chain),
    )
```

## 핵심 규칙

- `message`는 항상 **클래스 속성**으로 정의 (`ClassVar` 타입 힌트는 루트 클래스에만)
- **에러는 구조화된 데이터, 서술적 텍스트가 아님** — 상세 내용은 로그에서 처리
- **f-string으로 서술적 에러 메시지를 작성하지 마세요**
- **`__str__`을 오버라이드하지 마세요** — 클래스 `message` 속성 사용
- `__init__` 오버라이드 시 반드시 `super().__init__()` 호출
- 추상 베이스 클래스는 `ABC` 다중 상속, 본문은 `...` (Ellipsis)

## 금지 사항

- `TypeError`, `ValueError` 등 빌트인 예외를 직접 raise하지 마세요. 커스텀 에러를 정의하세요.
- `ClassVar[str]`은 루트 `AbstractSpakkyFrameworkError`에만 사용합니다. 하위 클래스에서는 단순히 `message = "..."`.
- **`__str__`을 오버라이드하여 서술적 메시지를 작성하지 마세요.**
- **f-string을 사용하여 에러 메시지를 descriptive하게 작성하지 마세요.**
