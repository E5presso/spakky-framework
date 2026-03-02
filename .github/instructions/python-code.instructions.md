---
applyTo: "**/*.py"
---

# Python 코딩 표준

이 규칙은 모든 Python 파일에 자동 적용됩니다.

## Type Safety (절대 규칙)

- `Any` 타입 **사용 금지**. `TypeVar`, `Protocol`, `object`, `Union`을 사용하세요.
- `Any`가 허용되는 유일한 경우: 외부 라이브러리의 invariant generics로 불가피한 경우, 반드시 인라인 주석으로 사유를 명시.
- `# type: ignore` 주석은 **절대 금지**. 올바른 type-safe 해법을 찾으세요.

## Unreachable States (불가능한 상태 처리)

**불가능한 상태는 조용히 넘어가지 말고 명시적으로 실패하라.**

- Silent fallback 금지 (`_ => default`, `return None`, `pass`)
- `typing.assert_never()` 또는 `raise AssertionError("explanation")` 사용
- defensive programming으로 불가능한 케이스를 처리하지 마세요
- **조용히 잘못된 결과를 내는 것보다 크래시가 낫다**

```python
from typing import assert_never

# BAD: Silent fallback
match event_type:
    case EventType.DOMAIN:
        handle_domain()
    case _:
        pass  # 무슨 타입이든 무시?

# GOOD: Exhaustive match with assert_never
match event_type:
    case EventType.DOMAIN:
        handle_domain()
    case EventType.INTEGRATION:
        handle_integration()
    case _ as unreachable:
        assert_never(unreachable)
```

## Import 규칙

- **상단 import 사용**: 파일 최상단에 `import` / `from ... import ...` 작성
- **Inline qualified path 금지**: `spakky.core.pod.Pod` 형태로 인라인 사용 금지
- 이름 충돌 시에만 예외: `from sqlalchemy import Column as SAColumn`

```python
# BAD: inline qualified path
def create_pod() -> spakky.core.pod.annotations.pod.Pod:
    ...

# GOOD: top-level import
from spakky.core.pod.annotations.pod import Pod

def create_pod() -> Pod:
    ...
```

## 기존 헬퍼/유틸리티 확인

새 헬퍼나 유틸리티를 작성하기 전에:

1. 먼저 기존 코드베이스에서 유사한 기능이 있는지 검색
2. 특히 `spakky.core` 패키지의 유틸리티 확인
3. 중복 구현 방지 — DRY 원칙

## 네이밍 규칙

- **패키지**: `snake_case` (예: `spakky.plugins.fastapi`)
- **클래스**: `PascalCase` (예: `UserController`)
- **함수/메서드**: `snake_case` (예: `get_user`)
- **Protocol (인터페이스)**: `I` 접두사 (예: `IIntegrationEventPublisher`, `IContainer`)
- **Abstract 클래스**: `Abstract` 접두사 (예: `AbstractEntity`, `AbstractEvent`)
- **Error 클래스**: `Error` 접미사 (예: `CannotDeterminePodTypeError`)

## 매직 넘버 금지

매직 넘버를 사용하지 마세요. 명명된 상수를 docstring과 함께 정의하세요.

```python
# BAD
return String(length=255)

# GOOD
DEFAULT_STRING_LENGTH: int = 255
"""Default length for fallback String column type."""
return String(length=DEFAULT_STRING_LENGTH)
```

**예외**: `0`, `1`, `-1`은 명확한 맥락에서 허용 (예: `range(0, n)`, `index + 1`).

## 로깅

- 모듈 레벨에서 `getLogger(__name__)` 사용.
- 생성자나 DI로 로거를 주입하지 마세요.

## Docstring

Google Python Style Guide를 따르세요.

```python
def fetch_user(user_id: int) -> User | None:
    """Fetch a user by ID.

    Args:
        user_id: The unique identifier.

    Returns:
        The User object if found, None otherwise.
    """
```

## Python 빌트인 충돌 방지

- 빌트인 이름과 겹치는 클래스명을 피하세요.
- `from enum import Enum as PyEnum` 같은 빌트인 앨리어싱은 **금지**입니다.
- 충돌이 있으면 커스텀 클래스의 이름을 변경하세요 (예: `Enum` → `EnumField`).
