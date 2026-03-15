# ADR-0006: spakky-outbox를 core 패키지로 승격

- **상태**: Accepted
- **날짜**: 2026-03-15
- **관련**: [ADR-0002](0002-outbox-plugin-architecture.md), [ADR-0005](0005-merge-outbox-sqlalchemy-into-sqlalchemy.md)

## 맥락 (Context)

ADR-0005에서 `spakky-outbox-sqlalchemy` 구현체를 `spakky-sqlalchemy`로 통합한 결과, `spakky-outbox`에는 순수 추상화와 오케스트레이션만 남았다:

- **포트**: `IOutboxStorage`, `IAsyncOutboxStorage` (인터페이스)
- **오케스트레이션**: `OutboxEventBus` (IEventBus 대체), `OutboxRelayBackgroundService`
- **설정**: `OutboxConfig`
- **메시지**: `OutboxMessage` (데이터 클래스)

인프라 의존이 완전히 제거된 상태에서, `plugins/`에 유지하는 것이 적절한지 재평가가 필요하다.

## 결정 동인 (Decision Drivers)

- **일관성**: `spakky-data`(추상화: Repository, Transaction)와 `spakky-event`(추상화: EventBus, EventTransport)가 이미 core에 있음. 같은 추상화 수준인 outbox도 core가 자연스러움
- **의존 방향**: outbox는 `spakky-event`에만 의존 → core chain에 자연스럽게 편입
- **대칭성**: `spakky-task`도 모든 앱이 쓰지 않는 선택적 패턴이지만 core에 있음. 기준이 일관되어야 함

## 고려한 대안 (Considered Options)

### 대안 A: plugins/에 유지

현상 유지. outbox는 선택적 기능이므로 플러그인으로 분류.

- **장점**: 변경 없음
- **단점**: `spakky-data`, `spakky-task`와 동일 수준의 추상화인데 분류가 다름. "왜 outbox만 plugin인가?"에 대한 합리적 답변 부재

### 대안 B: core/로 이동

`plugins/spakky-outbox` → `core/spakky-outbox`로 이동. import 경로를 `spakky.plugins.outbox` → `spakky.outbox`로 변경.

- **장점**: data/event/task와 동일한 추상화 계층으로 일관된 분류. core chain에서 `event` 다음 위치가 자연스러움
- **단점**: Breaking change — import 경로 변경

## 결정 (Decision)

**대안 B 채택**: `spakky-outbox`를 `core/`로 이동한다.

핵심 근거:

1. 인프라 구현이 모두 제거되어 순수 추상화만 남음
2. `spakky-data` (Repository 추상화), `spakky-event` (EventBus 추상화)와 동일한 레벨
3. 의존 체인: `spakky` → `domain` → `data` → `event` → **`outbox`** → `task`

### 마이그레이션 계획

1. `plugins/spakky-outbox/` → `core/spakky-outbox/`로 디렉토리 이동
2. import 경로 변경: `spakky.plugins.outbox` → `spakky.outbox`
3. 모노레포 설정 업데이트 (pyproject.toml, code-workspace)
4. `spakky-sqlalchemy`의 런타임 감지 import 경로 업데이트
5. 의존성 선언 변경: `spakky-event>=6.0.0` (변경 없음, event의 다음 단계)

## 결과 (Consequences)

### 긍정적

- core/plugin 분류 기준이 명확해짐: **추상화 = core, 인프라 구현 = plugin**
- `spakky-task`와 동일한 패턴 (선택적 core 추상화)

### 부정적

- Breaking change: `spakky.plugins.outbox` → `spakky.outbox` import 경로 변경
- `spakky-sqlalchemy`의 outbox 런타임 감지 경로 수정 필요

### 중립적

- `pydantic-settings` 의존이 core에 추가됨 (이미 Spakky 프레임워크 전반에서 사용하는 라이브러리)
