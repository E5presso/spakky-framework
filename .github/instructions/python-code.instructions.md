---
applyTo: "**/*.py"
---

# Python 코딩 표준

## Type Safety (절대 규칙)

- `Any` **금지**. `TypeVar`, `Protocol`, `object`, `Union` 사용.
- `Any` 허용 예외: 외부 라이브러리 invariant generics — 인라인 주석으로 사유 명시.
- `# type: ignore` **절대 금지**.

### `# type: ignore` 허용 예외 (기존 코드)

아래 경우에만 기존 `# type: ignore` 유지 허용:

| 케이스 | 예시 |
|--------|------|
| 외부 라이브러리 타입 불완전 | `from aio_pika import ...  # type: ignore` |
| 테스트에서 의도적 타입 위반 | `invalid_input: Any = "wrong"  # type: ignore - 에러 테스트` |
| 런타임 동적 타입 | MRO 계산 등 타입 추론 불가능 코드 |

**새 코드에서는 절대 추가 금지.** 대안: `cast()`, `TypeVar`, `Protocol`, `overload`.

## Unreachable States

불가능한 상태는 명시적으로 실패 (silent fallback 금지):

```python
from typing import assert_never
match event_type:
    case EventType.DOMAIN: handle_domain()
    case EventType.INTEGRATION: handle_integration()
    case _ as unreachable: assert_never(unreachable)
```

## Import 규칙

- 파일 최상단 import 사용. 인라인 qualified path 금지 (`spakky.core.pod.Pod` 형태).
- 이름 충돌 시에만 alias 허용: `from sqlalchemy import Column as SAColumn`

## 네이밍

- **Protocol**: `I` 접두사 (`IContainer`, `IIntegrationEventPublisher`)
- **Abstract 클래스**: `Abstract` 접두사 (`AbstractEntity`, `AbstractEvent`)
- **Error 클래스**: `Error` 접미사 (`CannotDeterminePodTypeError`)
- 패키지 `snake_case`, 클래스 `PascalCase`, 함수/메서드 `snake_case`

## 매직 넘버 금지

명명된 상수로 정의. 예외: `0`, `1`, `-1` 명확한 맥락에서 허용.

## 기타

- 로깅: 모듈 레벨 `getLogger(__name__)` (DI 주입 금지)
- Docstring: Google Python Style Guide
- 빌트인 이름 충돌 시 커스텀 클래스 이름 변경 (`Enum` → `EnumField`). 빌트인 앨리어싱 금지.
- 기존 헬퍼 먼저 검색 (`spakky.core` 유틸리티 확인)

