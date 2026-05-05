# ADR-0010: Feature Contribution Policy

- **상태**: Accepted
- **날짜**: 2026-05-05
- **대체**: 해당 없음
- **선행 동기**: [ADR-0009](0009-agentic-hexagonal-architecture.md)

## 맥락 (Context)

Spakky Framework의 core 패키지는 항상 plugin을 통한 간접 설치를 전제로 한다. core는 사용자 DX 표면, 고수준 orchestration, policy, domain logic을 제공하지만, 데이터베이스, 메시지 브로커, 외부 SDK, 프로토콜 서버 같은 인프라 종속 저수준 구현은 plugin이 제공한다.

이 구조는 core와 plugin의 책임을 잘 분리하지만, 여러 core feature가 같은 인프라 plugin의 구현을 필요로 할 때 문제가 생긴다. 예를 들어 `spakky-sqlalchemy`는 `spakky-data` repository 구현뿐 아니라 `spakky-outbox` storage, 향후 `spakky-agent` checkpoint/evidence/artifact store 구현도 제공할 수 있다.

기존 선택지는 둘 다 불만족스럽다.

1. `spakky-sqlalchemy` 본체에서 `spakky-agent` 또는 `spakky-outbox` 설치 여부를 감지해 조건부 등록한다.
2. `spakky-agent-sqlalchemy`, `spakky-outbox-sqlalchemy`, `spakky-saga-sqlalchemy` 같은 feature-specific infra plugin을 계속 만든다.

첫 번째는 플러그인 본체가 다른 core feature의 설치 상태를 런타임 분기하는 코드스멜을 만든다. 두 번째는 동일한 SQLAlchemy 인프라 구현이 feature별 패키지로 폭증한다.

## 결정 동인 (Decision Drivers)

- 플러그인 간 직접 import 금지와 단방향 의존 규칙을 유지해야 한다.
- core feature는 고수준 계약과 orchestration을 소유할 수 있어야 한다.
- 인프라 plugin은 같은 인프라 substrate를 여러 core feature에 제공할 수 있어야 한다.
- feature별 infra plugin 폭증을 막아야 한다.
- 런타임 `try/except ImportError`, `_HAS_*` flag, 설치 상태 감지 분기를 만들지 않아야 한다.
- contribution 로딩은 entry point metadata로 선언되어야 하며, 설치 조합이 진단 가능해야 한다.

## 고려한 대안 (Considered Options)

### 대안 A: 인프라 plugin 본체에서 optional feature 감지

`spakky-sqlalchemy`가 `spakky-agent`, `spakky-outbox`, `spakky-saga` 설치 또는 Pod 등록 여부를 확인하고 필요한 구현체를 추가 등록한다.

장점:

- 새 패키지가 늘지 않는다.
- 구현 위치가 한 패키지 안에 모인다.

단점:

- plugin 본체가 여러 core feature를 알아야 한다.
- 설치 상태 감지 분기가 늘어난다.
- core feature가 추가될수록 `main.py`가 feature switchboard가 된다.
- “optional DI는 import 가능 여부가 아니라 Pod 등록 여부로 판단한다”는 기존 개선 방향을 다시 약화한다.

### 대안 B: feature-specific infra plugin 패키지

`spakky-agent-sqlalchemy`, `spakky-outbox-sqlalchemy`처럼 core feature와 infra plugin의 조합마다 별도 패키지를 만든다.

장점:

- 책임 경계가 명확하다.
- 로딩은 기존 plugin entry point만으로 가능하다.

단점:

- 패키지 수가 core feature × infra substrate 조합으로 폭증한다.
- 같은 인프라 설정, session, schema registry, migration helper가 반복된다.
- 사용자가 설치해야 할 패키지 조합을 이해하기 어렵다.

### 대안 C: Feature Contribution Policy

플러그인은 본체 plugin entry point와 별도로, core feature별 contribution entry point를 선언할 수 있다. framework loader는 활성 core feature에 대응하는 contribution group만 로드한다.

예:

```toml
[project.entry-points."spakky.plugins"]
spakky-sqlalchemy = "spakky.plugins.sqlalchemy.main:initialize"

[project.entry-points."spakky.contributions.spakky-outbox"]
sqlalchemy-outbox = "spakky.plugins.sqlalchemy.contributions.outbox:initialize"

[project.entry-points."spakky.contributions.spakky-agent"]
sqlalchemy-agent-state = "spakky.plugins.sqlalchemy.contributions.agent_state:initialize"
```

장점:

- `spakky-sqlalchemy` 패키지는 하나로 유지된다.
- feature별 구현 기여는 명시적 entry point로 분리된다.
- plugin 본체가 다른 core feature 설치 여부를 감지하지 않는다.
- loader가 누락 contribution을 구조적으로 진단할 수 있다.
- 향후 Redis, Kafka, SQLAlchemy 같은 인프라 plugin이 여러 core feature에 같은 방식으로 기여할 수 있다.

단점:

- plugin loader에 contribution discovery 단계가 추가된다.
- pyproject entry point naming, include filtering, diagnostics 규칙이 새로 필요하다.
- contribution module은 feature-specific core 계약을 import하므로 의존성 정책을 명확히 보강해야 한다.

## 결정 (Decision)

대안 C를 채택한다.

Spakky Framework는 **Feature Contribution Policy**를 도입한다. plugin package는 하나의 base plugin entry point와 0개 이상의 feature contribution entry point를 가질 수 있다. contribution은 특정 core feature가 정의한 extension point 또는 port 구현을 제공하는 선언적 기여 단위다.

정책:

- base plugin entry point group은 기존처럼 `spakky.plugins`를 사용한다.
- feature contribution entry point group은 `spakky.contributions.<feature-plugin-name>` 형식을 사용한다.
- `<feature-plugin-name>`은 core feature의 plugin name과 동일해야 한다. 예: `spakky-agent`, `spakky-outbox`.
- contribution entry point name은 같은 group 안에서 고유해야 한다.
- contribution module은 해당 feature core package의 public contract를 import할 수 있다.
- base plugin `initialize()`는 다른 feature 설치 여부를 감지하지 않는다.
- contribution `initialize()`도 다른 plugin을 직접 import하지 않고, feature core contract와 자기 plugin 내부 구현만 import한다.
- loader는 base plugin loading 이후 활성 feature contribution을 로드한다.
- `include`가 지정된 plugin loading에서는 base plugin과 contribution provider/plugin filtering semantics를 명시적으로 정의한다.
- `include`가 지정되면 target feature plugin과 contribution provider base plugin이 모두 `include`에 있고 실제 base plugin으로 로드된 경우에만 contribution을 로드한다.
- contribution provider base plugin은 contribution entry point name 파싱이 아니라 해당 entry point distribution의 `spakky.plugins` metadata로 식별한다.
- diagnostics는 로드된 contribution, skipped contribution, missing required contribution을 startup report에 기록할 수 있어야 한다.

## Canonical Loading Model

```text
Installed packages
  -> spakky.plugins entry points
  -> active core feature set
  -> spakky.contributions.<feature> entry points
  -> Pod/Tag registration
  -> ApplicationContext.start()
```

활성 core feature는 다음 중 하나로 결정한다.

- 해당 core feature plugin entry point가 로드되었다.
- 사용자가 `load_plugins(include=...)`로 해당 core feature를 명시 포함했다.
- 향후 loader API가 feature activation을 별도로 선언한다.

Contribution은 base plugin을 대체하지 않는다. base plugin은 인프라 substrate의 기본 설정과 공통 구현을 등록하고, contribution은 특정 core feature port 구현만 추가 등록한다.

## Consequences

### 긍정적

- feature-specific infra plugin 패키지 폭증을 막는다.
- optional feature 감지 분기와 `_HAS_*` flag 재발을 막는다.
- `spakky-sqlalchemy` 같은 인프라 plugin이 여러 core feature에 명시적으로 기여할 수 있다.
- `spakky-agent`는 durable state, checkpoint, evidence, artifact store를 core contract로 정의하고, SQLAlchemy 구현은 `spakky-sqlalchemy` contribution으로 받을 수 있다.
- plugin loader diagnostics가 설치 조합 문제를 설명할 수 있다.

### 부정적

- plugin loader가 단순 entry point loader에서 feature-aware loader로 확장된다.
- entry point naming policy와 contribution lifecycle을 새로 문서화해야 한다.
- 기존 `spakky-sqlalchemy`와 `spakky-outbox` 결합은 contribution 방식으로 마이그레이션해야 한다.

### 중립적

- 이 정책은 plugin 간 직접 import 허용을 의미하지 않는다.
- contribution은 feature core contract를 import할 수 있지만 다른 plugin public module을 import할 수 없다.
- contribution은 package split의 대체 수단이지, 모든 optional behavior의 만능 hook이 아니다.

## Agentic Hexagonal Architecture와의 관계

ADR-0009의 `spakky-agent`는 checkpoint/evidence/artifact persistence가 필수인 ambitious milestone이다. 그러나 agent 전용 SQLAlchemy plugin을 만들면 package 폭증 문제가 바로 발생한다.

따라서 ADR-0009 구현 전에 본 ADR을 먼저 구현한다.

`spakky-agent` milestone에서는 다음 전제를 사용한다.

- `core/spakky-agent`는 agent orchestration, policy, approval, evidence, convergence, durable state port를 소유한다.
- `plugins/spakky-pydantic-ai`는 reference execution backplane adapter를 제공한다.
- `plugins/spakky-sqlalchemy`는 `spakky.contributions.spakky-agent` contribution으로 agent durable state 구현을 제공한다.

## 검증 기준

- `spakky-sqlalchemy` base plugin은 `spakky-agent` 설치 여부를 감지하지 않는다.
- `spakky-sqlalchemy`는 `spakky.contributions.spakky-agent` entry point를 통해 agent persistence 구현을 기여할 수 있다.
- contribution loader는 active feature에 해당하는 contribution만 호출한다.
- contribution loader는 startup diagnostics에 contribution 로딩 결과를 기록한다.
- `load_plugins(include=...)` 사용 시 base plugin과 contribution filtering이 예측 가능하게 동작한다.
- 기존 outbox SQLAlchemy 구현은 contribution policy로 재배치 가능하다.

## 미결정 사항

- contribution entry point가 base plugin보다 먼저 로드될 수 없도록 보장하는 구체 순서
- contribution이 required인지 optional인지 feature core가 선언하는 API
- contribution diagnostics의 정확한 public model
