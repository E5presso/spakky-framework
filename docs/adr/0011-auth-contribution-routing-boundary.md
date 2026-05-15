# ADR-0011: Auth Contribution Routing Boundary

- **상태**: Proposed
- **날짜**: 2026-05-15
- **대체**: 해당 없음
- **관련**: [ADR-0010](0010-feature-contribution-policy.md), [인증/인가 마일스톤 스펙](../planning/auth-authorization-milestone-scope.md)

## 맥락 (Context)

인증/인가 마일스톤은 `spakky-auth` 코어 패키지와 provider plugin을 도입한다. 이 과정에서 여러 provider가 같은 capability를 제공할 수 있다. 예를 들어 policy evaluator, relation checker, snapshot signer, password verifier가 모두 `spakky.contributions.spakky.auth` contribution으로 들어올 수 있다.

ADR-0010은 feature contribution loading의 일반 정책이다. 그러나 인증/인가 마일스톤의 현재 구현 범위는 generic multi-contribution routing engine을 만드는 것이 아니다. 현재 마일스톤은 auth feature 내부에서 protected metadata와 snapshot propagation config가 요구하는 capability를 검증하고, 정확히 하나의 provider가 필요한 경우 startup에서 fail fast하는 데 집중한다.

따라서 본 ADR은 **미래의 generic contribution routing proposal**이다. 현재 인증/인가 구현의 SSOT (Single Source of Truth)는 이 ADR이 아니라 인증/인가 마일스톤과 자식 이슈 본문, 그리고 [인증/인가 마일스톤 스펙](../planning/auth-authorization-milestone-scope.md)이다.

## 결정 동인 (Decision Drivers)

- 여러 feature가 provider contribution을 요구할 때 routing 규칙이 feature마다 중복될 수 있다.
- provider 우선순위, qualifier, binding policy, diagnostics를 feature-neutral 형태로 재사용할 여지가 있다.
- 다만 인증/인가 마일스톤은 기존 코드와 충돌하지 않는 작은 단위로 진행되어야 한다.
- generic routing을 선행 구현하면 `spakky-auth`의 핵심 계약, AOP enforcement, provider/boundary integration보다 큰 선행 dependency가 생긴다.

## 제안 (Proposal)

향후 Spakky Framework는 feature contribution을 단순 loading 단위에서 routing 가능한 provider 후보 집합으로 확장할 수 있다.

제안 방향:

- feature core는 capability key와 selection policy를 선언한다.
- provider contribution은 capability set과 diagnostic metadata를 선언한다.
- application config 또는 feature-local metadata가 capability별 provider binding을 지정할 수 있다.
- routing 결과는 startup diagnostics에 후보, 선택 근거, 충돌 원인을 구조화해 기록한다.
- 단수 provider가 필요한 capability에서 후보가 0개 또는 2개 이상이면 startup failure로 처리한다.

이 제안은 ADR-0010의 contribution loading 이후 단계에 위치한다.

```text
spakky.plugins base loading
  -> active feature discovery
  -> spakky.contributions.<feature> loading
  -> future contribution routing proposal
  -> feature-local startup validation
  -> ApplicationContext.start()
```

## 현재 인증/인가 마일스톤에 적용하지 않는 범위

본 ADR은 현재 마일스톤에서 다음 구현을 요구하지 않는다.

- generic multi-contribution routing engine
- provider priority/routing DSL (Domain-Specific Language)
- Redis 또는 SQLAlchemy auth persistence contribution
- audit log platform
- approval grant lifecycle
- MCP (Model Context Protocol) runtime/tool authorization
- authorized data/query filtering
- OIDC browser login/callback/session/refresh/logout route
- OpenFGA tuple/model admin 또는 list-resources API

현재 인증/인가 구현은 `spakky-auth` feature-local validation으로 충분해야 한다. protected auth usage 또는 snapshot propagation config가 요구하는 capability마다 provider count를 검증하고, 0개 또는 2개 이상이면 structured auth startup error와 startup diagnostic detail로 실패한다. provider-specific priority/routing은 구현하지 않는다.

## 현재 마일스톤의 기준

현재 기준은 다음과 같다.

- `spakky-auth`는 provider-neutral model, ABC port, decorator metadata, AOP enforcement, feature-local startup validation을 소유한다.
- provider plugin은 `spakky.contributions.spakky.auth` contribution으로 capability를 제공한다.
- protected/decorated boundary는 fail closed이고 decorator가 없는 boundary는 allow all이다.
- task, broker, event, saga 전파는 raw bearer token이 아니라 signed `AuthContextSnapshot`을 사용한다.
- permission, role, scope, resource, action, claim, tenant 값은 string canonical ref로 둔다.
- public port는 ABC + `abstractmethod`를 사용하며 `Protocol`은 사용하지 않는다.
- Phase 3.5 Loop-3에서 통과한 DAG (Directed Acyclic Graph)와 scope는 [인증/인가 마일스톤 스펙](../planning/auth-authorization-milestone-scope.md)을 따른다.

## 고려한 대안 (Considered Options)

### 대안 A: ADR-0011을 현재 auth 구현 SSOT로 승격

장점:

- provider routing의 큰 그림을 한 번에 설명할 수 있다.

단점:

- 현재 마일스톤 범위보다 넓은 generic routing을 구현 전제로 만들 수 있다.
- #279 이후 티켓의 작은 DAG (Directed Acyclic Graph) 단위가 불필요하게 커진다.
- Redis/SQLAlchemy persistence, audit, approval, MCP runtime auth, data filtering 같은 범위 밖 항목이 auth core 작업으로 오인될 수 있다.

### 대안 B: ADR-0011을 만들지 않음

장점:

- 현재 구현 범위가 단순하게 유지된다.

단점:

- 향후 여러 feature가 provider routing 요구를 공유할 때 논의 출발점이 없다.
- ADR-0010과 auth feature-local validation 사이의 미래 확장 여지를 문서화하지 못한다.

### 대안 C: Future proposal로만 유지

장점:

- 현재 인증/인가 구현 범위와 미래 generic routing 논의를 분리한다.
- downstream issue는 feature-local validation과 provider/boundary integration에 집중할 수 있다.
- scope drift를 막으면서도 향후 generic routing 설계의 자리표시자를 남긴다.

단점:

- 향후 구현 시 별도 ADR 또는 본 ADR의 Accepted 전환 PR이 필요하다.

## 결정 (Decision)

대안 C를 채택한다.

ADR-0011은 현재 `Proposed` 상태의 future generic contribution routing proposal로 남긴다. 현재 인증/인가 마일스톤의 구현 SSOT가 아니며, #279 이후 티켓은 본 ADR을 필수 구현 대상으로 삼지 않는다.

현재 마일스톤에서 필요한 provider count 검증은 `spakky-auth` feature-local startup validation으로 구현한다. generic routing engine, provider priority, Redis/SQLAlchemy auth persistence contribution, audit, approval, MCP runtime auth, data filtering은 모두 범위 밖이다.

## Consequences

### 긍정적

- 인증/인가 마일스톤의 현재 구현 범위가 작고 검증 가능하게 유지된다.
- ADR-0010 contribution loading 정책과 충돌하지 않는다.
- 향후 generic routing이 필요해질 때 논의 대상과 비대상을 분리한 출발점이 생긴다.

### 부정적

- provider routing을 원하는 future feature는 당장 공통 routing API를 재사용할 수 없다.
- provider priority가 필요한 요구는 현재 마일스톤에서 의도적으로 거절되어야 한다.

### 중립적

- `spakky-auth`는 contribution loading 이후 자체 validation을 수행한다.
- `spakky-policy`, `spakky-openfga`, `spakky-oidc`, `spakky-cryptography`는 provider-specific routing DSL 없이 capability를 제공한다.

## 검증 기준

- ADR-0011 본문은 현재 auth 구현 SSOT가 아님을 명시한다.
- 범위 밖 항목이 Redis/SQLAlchemy auth persistence contribution, audit, approval, MCP runtime auth, data filtering을 포함한다.
- 현재 마일스톤의 DAG (Directed Acyclic Graph)와 scope 기준은 별도 스펙 문서로 연결된다.
- `uv run mkdocs build --strict`가 통과한다.
