---
paths:
  - "**/*.py"
---

# Python 코딩 표준

## 타입 안전

- `Any` **금지**. `TypeVar`, `Protocol`, `object`, `Union` 사용.
- `Any` 허용 예외: 외부 라이브러리 invariant generics — 인라인 주석으로 사유 명시.

## 에러

- 프레임워크 내 모든 에러 클래스는 `AbstractSpakkyFrameworkError` 가족을 상속
- `src/` 내에서 빌트인 예외(`TypeError`, `ValueError` 등)를 직접 `raise` 금지 — 커스텀 에러 정의
- 불가능한 상태도 커스텀 에러로 실패 (silent fallback 금지)

## 에러 정의 규칙

- `message`는 항상 **클래스 속성**으로 정의 (`ClassVar` 타입 힌트는 루트 클래스에만)
- 추가 컨텍스트 불필요 시 `message`만 정의. `__init__` 오버라이드 금지
- 컨텍스트 필요 시 `__init__` 오버라이드 + `super().__init__()` 호출 필수
- `__str__` 오버라이드 금지 — 상세 메시지는 로그에서 처리
- f-string으로 서술적 에러 메시지 작성 금지
- 추상 베이스 클래스는 `ABC` 다중 상속, 본문은 `...` (Ellipsis)

## 옵트아웃 주석

비활성화(opt-out) 주석에는 **반드시 사유를 포함**:

| 주석 | 올바른 예시 |
|------|------------|
| `# type: ignore` | `# type: ignore[arg-type] - aio_pika 타입 스텁 불완전` |
| `# pyrefly: ignore` | `# pyrefly: ignore - false positive on dynamic attr` |
| `# pragma: no cover` | `# pragma: no cover - exhaustive StrEnum` |
| `# pragma: no branch` | `# pragma: no branch - AbstractMethod only` |

## 네이밍

- **인터페이스**: `I` 접두사 (`IContainer`, `IEventPublisher`)
- **Abstract 클래스**: `Abstract` 접두사 (`AbstractEntity`, `AbstractEvent`)
- **Error 클래스**: `Error` 접미사 (`CannotDeterminePodTypeError`)
- **Async**: `Async` 접두사 (`AsyncTransactionalAspect`, `AsyncRabbitMQEventPublisher`)
- 패키지 `snake_case`, 클래스 `PascalCase`, 함수/메서드 `snake_case`

### 상속 타입 접미사 규칙

구현 클래스는 **상속받은 클래스/인터페이스의 역할 타입을 접미사**로 표기:

| 상속 타입 | 접미사 | 예시 |
|----------|--------|------|
| `IAsyncAspect` | `~Aspect` | `AsyncTransactionalAspect` |
| `AbstractAsyncBackgroundService` | `~BackgroundService` | `AsyncOutboxRelayBackgroundService` |
| `IPostProcessor` | `~PostProcessor` | `RegisterRoutesPostProcessor` |
| `AbstractAsyncTransaction` | `~Transaction` | `AsyncTransaction` |

**예외 — 도메인 모델**: 도메인 모델은 고유 용어(유비쿼터스 언어)를 사용. 접미사 없음.

### Generic 타입 네로잉

Generic 인터페이스 상속 시, 타입 파라미터가 구체화되면 해당 타입명으로 대체:
- `UserRepository(IAsyncGenericRepository[User, UUID])` ✅
- `UserGenericRepository(...)` ❌

## Import 규칙

- 파일 최상단 import 사용. 인라인 qualified path 금지.
- 이름 충돌 시에만 alias 허용: `from sqlalchemy import Column as SAColumn`

## 하위 호환성

- **Breaking change 우선**: 사용자가 명시적으로 허가하지 않는 한, 하위 호환성 유지하지 않음
- **Alias 금지**: `OldName = NewName` 형태의 하위 호환 alias 금지
- 리네이밍 시 모든 사용처를 **일괄 수정**

## Override

- 부모 클래스 메서드를 재정의할 때 `@override` 데코레이터 필수 (`from typing import override`)
- ABC abstract method 구현에도 적용

## assert 문

- `src/` 내에서 `assert` 금지 — 런타임 검증은 커스텀 에러로 처리
- `tests/` 내에서만 허용

## 동적 속성 접근

- `getattr()`, `hasattr()`, `setattr()` 사용 금지 — 타입 안전성 파괴
- 허용 예외: 프레임워크 내부 메타클래스/데코레이터 구현 — 인라인 주석으로 사유 명시

## 테스트 커버리지 의무

- `src/` 코드를 작성하거나 수정하면 **반드시 관련 테스트 코드를 함께 작성**하여 브랜치 커버리지 100%를 달성한다
- 테스트 없이 프로덕션 코드만 커밋 금지
- 새 모듈/클래스 추가 시 대응하는 테스트 파일을 동시에 생성
- 기존 코드 수정 시 영향받는 테스트가 모든 분기를 커버하는지 확인

## 기타

- 모듈 레벨 `def _helper()` 대신 클래스 메서드로 배치
- 동기/비동기 쌍에서 동일 로직이 반복되더라도 각 클래스에 인라인 — 의도적 중복 허용
- silent fallback 금지: `pass`, `return None`, 기본값 반환 금지
- 로깅: 모듈 레벨 `getLogger(__name__)` (DI 주입 금지)
- Docstring: Google Python Style Guide
- 매직 넘버 금지 — 명명된 상수로 정의
- 기존 헬퍼 먼저 검색 (`spakky.core` 유틸리티 확인)
