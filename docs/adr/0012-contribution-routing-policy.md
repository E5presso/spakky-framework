# ADR-0012: Contribution 라우팅 정책

- **상태**: Proposed
- **날짜**: 2026-05-10
- **대체**: 해당 없음
- **관련**: [ADR-0010](0010-feature-contribution-policy.md), [ADR-0011](0011-auth-contribution-routing-boundary.md)

## 맥락

ADR-0010은 플러그인 패키지가 코어 기능별 contribution entry point를 제공할 수 있게 하여 기능별 인프라 플러그인 폭증을 줄였다. 그러나 현재 contribution 로딩 모델은 contribution을 발견하고 로드하는 정책에 집중한다. 같은 기능에 대해 여러 제공자 contribution이 동시에 활성화되었을 때, 프레임워크 코어가 어떤 contribution을 선택해야 하는지에 대한 일반 라우팅 정책은 아직 없다.

Spakky 인증/인가 기획 중 여러 플러그인이 같은 기능 capability를 제공할 때 프레임워크가 어느 contribution을 선택해야 하는지에 대한 일반 문제가 드러났다. 예를 들어 향후 어떤 기능이 durable store, transient cache, external policy decision point처럼 서로 다른 의미의 contribution을 동시에 요구할 수 있다. 이 조합은 정상적인 운영 구성이지만, 단순히 "같은 capability 제공자가 복수 활성화되면 fail-fast"로 처리하면 정상적인 플러그인 조합도 부팅하지 못할 수 있다.

다만 현재 인증/인가 마일스톤에서 프레임워크 코어 수준의 범용 multi-contribution 라우팅까지 구현하는 것은 범위를 과도하게 키운다. 현재 인증/인가 마일스톤은 사용자 인증·인가 계약, 제공자 중립 enforcement, OIDC/policy/OpenFGA/cryptography 제공자, inbound boundary 통합에 집중한다. 인증 영속성, Redis/SQLAlchemy 인증 contribution, 감사 로그, 승인 grant, token/session 저장소, authorized data filtering은 이 ADR의 미래 라우팅 논의와 별개로 현재 마일스톤 범위 밖이다.

## 결정 동인

- 정상적인 플러그인 조합이 contribution 충돌로 부팅 실패하지 않아야 한다.
- 코어 기능은 제공자 플러그인 이름을 직접 알거나 문자열로 분기하지 않아야 한다.
- contribution 선택은 프레임워크 코어에서 일관되게 진단 가능해야 한다.
- 기능별 ad hoc 라우팅 API를 패키지마다 만들지 않아야 한다.
- 현재 인증/인가 마일스톤은 인증/인가 계약과 제공자 중립 enforcement에 집중해야 한다.

## 고려한 대안

### 대안 A: 같은 contribution capability 중복 시 항상 fail-fast

같은 기능 capability를 제공하는 contribution이 둘 이상이면 프레임워크가 즉시 실패한다.

장점:

- 구현이 단순하다.
- 모호한 provider 선택을 silent하게 지나치지 않는다.

단점:

- SQLAlchemy durable store와 Redis transient cache처럼 함께 쓰는 것이 자연스러운 조합도 실패할 수 있다.
- feature가 capability를 거칠게 정의할수록 false conflict가 늘어난다.
- 사용자는 정상적인 plugin 조합에서도 불필요한 장애를 만난다.

### 대안 B: feature별 ad hoc routing

`spakky-auth`, `spakky-agent`, `spakky-outbox` 같은 각 기능이 자기 라우팅 규칙을 별도로 구현한다.

장점:

- 기능별 요구사항을 빠르게 반영할 수 있다.
- 프레임워크 코어 변경 없이 시작할 수 있다.

단점:

- contribution 선택 규칙이 기능마다 달라진다.
- 진단, 오류 메시지, 설정 표면이 중복된다.
- 코어가 제공자 이름을 모르도록 한다는 원칙이 각 기능에서 다시 흔들릴 수 있다.

### 대안 C: 프레임워크 코어 차원의 contribution 라우팅 정책

프레임워크 코어가 contribution descriptor를 수집하고, 기능이 요구하는 port/capability/semantic에 따라 contribution을 선택하는 공통 라우팅 정책을 제공한다.

장점:

- contribution 충돌 탐지와 선택 규칙이 framework 전체에서 일관된다.
- 기능 코어는 제공자 플러그인 이름을 몰라도 된다.
- SQLAlchemy durable contribution과 Redis transient contribution처럼 정상적인 조합을 표현할 수 있다.
- startup diagnostics에 contribution 선택과 미선택 사유를 구조화해 남길 수 있다.

단점:

- 프레임워크 코어 contribution loader와 diagnostics가 더 복잡해진다.
- contribution descriptor schema, semantic vocabulary, routing policy object가 필요하다.
- 기존 ADR-0010 loader 정책 위에 별도 마일스톤이 필요하다.

## 결정

대안 C를 미래 방향으로 제안한다. 다만 이 ADR은 Proposed 상태이며, 현재 Auth 마일스톤의 구현 범위에 포함하지 않는다.

현재 인증/인가 마일스톤에서는 다음 임시 정책을 적용한다.

- 범용 contribution 라우팅은 구현하지 않는다.
- auth persistence contribution은 제공하지 않는다.
- `spakky-sqlalchemy`와 `spakky-redis`는 이번 인증/인가 마일스톤에서 auth contribution을 제공하지 않는다.
- 제공자 중립 auth capability 중복은 현재 마일스톤에서 기능 한정 startup validation으로 fail-fast한다.
- 따라서 인증/인가 마일스톤 안에서는 Redis/SQLAlchemy auth contribution conflict가 발생하지 않는다.

향후 contribution 라우팅 정책 마일스톤은 다음 방향을 검토한다.

- contribution descriptor가 제공 port, capability, durability, cache/transient/durable semantic, priority hint, feature compatibility를 선언한다.
- 프레임워크 코어가 활성 contribution set을 수집하고, 기능별 required contract에 맞춰 선택한다.
- 자동 선택 가능한 조합은 자동으로 선택하고, 의미상 동등한 후보가 복수이면 fail-fast한다.
- 라우팅 실패는 기능별 ad hoc error가 아니라 프레임워크 startup diagnostics로 보고한다.
- 라우팅 정책은 제공자 플러그인 이름 문자열이 아니라 typed descriptor와 semantic vocabulary를 기준으로 동작한다.

## 결과

### 긍정적

- 인증/인가 마일스톤의 범위가 사용자 인증·인가 core, provider, inbound boundary integration으로 고정된다.
- 향후 정상적인 multi-provider 조합을 프레임워크 차원에서 다룰 여지를 보존한다.
- 기능별 임시 라우팅 API가 늘어나는 것을 방지한다.

### 부정적

- 이번 인증/인가 마일스톤에서는 Redis auth session/token/revocation cache를 제공하지 않는다.
- 이번 인증/인가 마일스톤에서는 SQLAlchemy auth persistence contribution도 제공하지 않는다.
- multi-contribution 라우팅이 필요한 사용자는 후속 라우팅 마일스톤을 기다려야 한다.

### 중립적

- ADR-0010의 feature contribution loading 정책은 유지된다.
- 이 ADR은 contribution을 어떻게 발견할지보다, 발견된 contribution을 어떻게 선택할지에 초점을 둔다.
- 인증/인가 마일스톤의 Redis/SQLAlchemy auth persistence 관련 티켓은 생성하지 않는다.

## 참고 자료

- [ADR-0010: Feature Contribution Policy](0010-feature-contribution-policy.md)
