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

## 복잡 에러 (컨텍스트 정보 필요)

`__init__`, `__str__`을 오버라이드하고, 컨텍스트를 인스턴스 속성으로 저장합니다.

```python
class CircularDependencyGraphDetectedError(AbstractSpakkyPodError):
    """Raised when circular dependency is detected."""

    message = "Circular dependency graph detected"

    def __init__(self, dependency_chain: list[type]) -> None:
        super().__init__()
        self.dependency_chain = dependency_chain

    def __str__(self) -> str:
        lines = [self.message, "Dependency path:"]
        for i, type_ in enumerate(self.dependency_chain):
            type_name = type_.__name__
            indent = "  " * i
            arrow = "└─> " if i > 0 else ""
            lines.append(f"{indent}{arrow}{type_name}")
        return "\n".join(lines)
```

## 핵심 규칙

- `message`는 항상 **클래스 속성**으로 정의 (`ClassVar` 타입 힌트는 루트 클래스에만)
- `__init__` 오버라이드 시 반드시 `super().__init__()` 호출
- 컨텍스트 정보는 인스턴스 속성으로 저장 (프로그래밍적 접근 가능)
- `__str__`은 사람이 읽을 수 있는 메시지, `__repr__`은 디버깅용 (선택)
- 추상 베이스 클래스는 `ABC` 다중 상속, 본문은 `...` (Ellipsis)

## 금지 사항

- `TypeError`, `ValueError` 등 빌트인 예외를 직접 raise하지 마세요. 커스텀 에러를 정의하세요.
- `ClassVar[str]`은 루트 `AbstractSpakkyFrameworkError`에만 사용합니다. 하위 클래스에서는 단순히 `message = "..."`.
