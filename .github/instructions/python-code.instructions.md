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

불가능한 상태는 `assert_never()` 또는 `raise AssertionError()`로 명시적 실패 (silent fallback 금지).

## Import 규칙

- 파일 최상단 import 사용. 인라인 qualified path 금지 (`spakky.core.pod.Pod` 형태).
- 이름 충돌 시에만 alias 허용: `from sqlalchemy import Column as SAColumn`

## 네이밍

- **Protocol**: `I` 접두사 (`IContainer`, `IIntegrationEventPublisher`)
- **Abstract 클래스**: `Abstract` 접두사 (`AbstractEntity`, `AbstractEvent`)
- **Error 클래스**: `Error` 접미사 (`CannotDeterminePodTypeError`)
- **Async**: `Async` 접두사 (`AsyncTransactionalAspect`, `AsyncRabbitMQEventPublisher`)
- 패키지 `snake_case`, 클래스 `PascalCase`, 함수/메서드 `snake_case`

### 상속 타입 접미사 규칙

구현 클래스는 **상속받은 클래스/인터페이스의 역할 타입을 접미사**로 표기합니다.

| 상속 타입 | 접미사 | 예시 |
|----------|--------|------|
| `IAsyncAspect` | `~Aspect` | `AsyncTransactionalAspect` |
| `AbstractAsyncBackgroundService` | `~BackgroundService` | `AsyncOutboxRelayBackgroundService` |
| `IPostProcessor` | `~PostProcessor` | `RegisterRoutesPostProcessor` |
| `AbstractAsyncTransaction` | `~Transaction` | `AsyncTransaction` |

**예외 — 도메인 모델**: 도메인 모델은 고유 용어(유비쿼터스 언어)를 사용. `User`, `OrderPlaced`, `Money` 등 접미사 없음.

### 도메인 이벤트 네이밍

- **DomainEvent**: **과거분사형**만 사용. `DomainEvent` 접미사 금지.
  - `OrderPlaced` ✅ / `OrderPlacedDomainEvent` ❌
  - `UserCreated` ✅ / `UserCreatedEvent` ❌
- **IntegrationEvent**: `IntegrationEvent` 접미사 사용.
  - `OrderConfirmedIntegrationEvent` ✅

### Generic 타입 네로잉

Generic 인터페이스 상속 시, 타입 파라미터가 구체화되면 해당 타입명으로 대체:
- `UserRepository(IAsyncGenericRepository[User, UUID])` ✅
- `UserGenericRepository(...)` ❌

## 매직 넘버 금지

명명된 상수로 정의. 예외: `0`, `1`, `-1` 명확한 맥락에서 허용.

## 기타

- 로깅: 모듈 레벨 `getLogger(__name__)` (DI 주입 금지)
- Docstring: Google Python Style Guide
- 빌트인 이름 충돌 시 커스텀 클래스 이름 변경 (`Enum` → `EnumField`). 빌트인 앨리어싱 금지.
- 기존 헬퍼 먼저 검색 (`spakky.core` 유틸리티 확인)

