---
applyTo: "**"
excludeAgent: "cloud-agent"
---

# Copilot Code Review Instructions

Spakky Framework는 Spring‑inspired DI/IoC Python 프레임워크(3.11+)입니다.
`uv` 모노레포로 구성되며 `core/`(코어 패키지)와 `plugins/`(플러그인 패키지)로 나뉩니다.

---

## 리뷰 언어

- 리뷰 코멘트는 **한국어**로 작성합니다.

---

## 패키지 의존 방향 (단방향)

```
spakky → spakky-domain → spakky-data → spakky-event → spakky-outbox
spakky → spakky-tracing → spakky-event
spakky → spakky-task
```

- **역방향 의존 금지**: 하위 패키지가 상위 패키지를 import하면 지적합니다.
- **플러그인 → 플러그인 직접 import 금지**: 플러그인 간 의존은 반드시 코어 추상화를 거쳐야 합니다.
- **도메인 레이어(`**/domain/**`)에서 인프라 의존 import 금지**: SQLAlchemy, httpx, aiokafka 등.

---

## 타입 안전

- **`Any` 사용 금지**. `TypeVar`, `Protocol`, `object`, `Union`을 사용합니다.
  - 허용 예외: 외부 라이브러리 invariant generics — 반드시 인라인 주석으로 사유를 명시해야 합니다.
- **`# type: ignore` 금지**. 타입 안전한 해결책을 찾아야 합니다.

---

## 에러 처리

- 프레임워크 에러 클래스는 반드시 `AbstractSpakkyFrameworkError` 가족을 상속합니다.
- `src/` 내에서 빌트인 예외(`TypeError`, `ValueError` 등)를 직접 `raise` 금지합니다.
- **silent fallback 금지**: 빈 `pass`, `return None`, 기본값 반환으로 실패를 숨기면 안 됩니다.
- **`__str__` 오버라이드 금지**: 에러 클래스에서 `__str__`을 오버라이드하면 안 됩니다.
- **f‑string 에러 메시지 금지**: `message`는 클래스 속성으로 정의합니다.
- 구조화된 에러 데이터가 필요하면 `__init__`을 오버라이드하되 반드시 `super().__init__()` 호출합니다.

---

## 옵트아웃 주석

아래 주석에는 반드시 **사유**가 포함되어야 합니다. 사유 없이 사용되면 지적합니다.

| 주석                  | 예시                                                   |
| --------------------- | ------------------------------------------------------ |
| `# type: ignore`      | `# type: ignore[arg-type] - aio_pika 타입 스텁 불완전` |
| `# pyrefly: ignore`   | `# pyrefly: ignore - false positive on dynamic attr`   |
| `# pragma: no cover`  | `# pragma: no cover - exhaustive StrEnum`              |
| `# pragma: no branch` | `# pragma: no branch - AbstractMethod only`            |

---

## 네이밍 규칙

| 대상            | 규칙              | 예시                              |
| --------------- | ----------------- | --------------------------------- |
| 인터페이스      | `I` 접두사        | `IContainer`, `IEventPublisher`   |
| Abstract 클래스 | `Abstract` 접두사 | `AbstractEntity`, `AbstractEvent` |
| Error 클래스    | `Error` 접미사    | `CannotDeterminePodTypeError`     |
| Async 클래스    | `Async` 접두사    | `AsyncTransactionalAspect`        |
| 패키지          | `snake_case`      | `spakky.plugins.fastapi`          |
| 클래스          | `PascalCase`      | `UserController`                  |
| 함수/메서드     | `snake_case`      | `get_user`                        |

### 상속 타입 접미사

구현 클래스는 상속받은 인터페이스/클래스의 역할 타입을 접미사로 표기합니다.

| 상속 타입                        | 접미사               | 예시                                |
| -------------------------------- | -------------------- | ----------------------------------- |
| `IAsyncAspect`                   | `~Aspect`            | `AsyncTransactionalAspect`          |
| `AbstractAsyncBackgroundService` | `~BackgroundService` | `AsyncOutboxRelayBackgroundService` |
| `IPostProcessor`                 | `~PostProcessor`     | `RegisterRoutesPostProcessor`       |

**예외**: 도메인 모델은 유비쿼터스 언어를 사용하므로 접미사 없음.

### 도메인 이벤트

- **DomainEvent**: 과거분사형, 접미사 없음 (`OrderPlaced` ✅ / `OrderPlacedEvent` ❌)
- **IntegrationEvent**: `IntegrationEvent` 접미사 (`OrderConfirmedIntegrationEvent` ✅)

### Generic 타입 네로잉

Generic 인터페이스를 구체 타입으로 상속 시, 네로잉된 타입명으로 대체합니다.

- `UserRepository(IAsyncGenericRepository[User, UUID])` ✅
- `UserGenericRepository(...)` ❌

---

## AOP Aspect

- **동기/비동기 쌍 필수**: Aspect는 항상 동기(`IAspect`) + 비동기(`IAsyncAspect`) 쌍으로 구현합니다. 한쪽만 존재하면 지적합니다.
- `@Order(n)` 데코레이터 필수: 낮은 값 = 외부 래퍼.
- Aspect에서 직접 DB 쓰기 / 외부 API 호출 금지 — 의존성 주입으로 처리합니다.

---

## 도메인 레이어

- Entity/AggregateRoot: `next_id()` 클래스 메서드 필수.
- ValueObject: `validate()` 필수, 모든 필드는 hashable (mutable 컨테이너 금지).
- Event: `@immutable` (frozen dataclass), 변경 불가.
- 도메인 객체에서 I/O 수행 금지.

---

## 플러그인

- 엔트리 포인트: `main.py`의 `initialize(app: SpakkyApplication)` 함수.
- `__init__.py`에 공개 API 직접 노출 금지.
- `initialize`에서 동기 I/O 금지.
- 다른 플러그인 직접 import 금지.

---

## 테스트

- **함수 기반만 허용**: `class TestXxx` 패턴 금지.
- **docstring 필수**: 모든 테스트 함수에 docstring을 작성합니다.
- **네이밍**: `test_<대상>_<시나리오>_expect_<기대결과>`.
- 공통 fixture는 `conftest.py`에 정의합니다.
- Unit은 `tests/unit/`, Integration은 `tests/integration/`에 위치합니다.

---

## 코드 스타일

- **매직 넘버 금지**: 명명된 상수로 정의합니다 (`0`, `1`, `-1` 등 명백한 경우 제외).
- **import**: 파일 최상단. 인라인 qualified path 금지. 충돌 시에만 alias 허용.
- **로깅**: 모듈 레벨 `getLogger(__name__)`. DI로 주입하지 않습니다.
- **Docstring**: Google Python Style Guide.
- 동기/비동기 쌍에서 동일 로직이 반복되어도 각 클래스에 인라인합니다 (의도적 중복 허용).

---

## PR 리뷰 체크포인트

1. **레이어 의존 방향**: 역방향 의존이나 플러그인 간 직접 참조가 없는지 확인합니다.
2. **타입 안전**: `Any` 미사유 사용, `# type: ignore` 미사유 사용을 확인합니다.
3. **에러 처리**: 커스텀 에러 상속, silent fallback, `__str__` 오버라이드를 확인합니다.
4. **네이밍**: 접두사/접미사 규칙, 도메인 이벤트 명명을 확인합니다.
5. **테스트**: 함수 기반, docstring, 네이밍 패턴을 확인합니다.
6. **Aspect**: 동기/비동기 쌍 존재 여부를 확인합니다.
7. **Simplicity**: 요청 범위를 넘는 변경, 불필요한 추상화가 없는지 확인합니다.
8. **엣지 케이스**: None 체크 없는 Optional 접근, 빈 컬렉션 미처리를 확인합니다.

문제가 없으면 PR을 승인합니다.
