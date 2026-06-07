# Authentication and Authorization Milestone Scope

- **상태**: Active scope baseline
- **작성일**: 2026-05-15
- **대상 마일스톤**: 프레임워크 인증/인가
- **관련 ADR**: [ADR-0011](../adr/0011-auth-contribution-routing-boundary.md)

## 목적

이 문서는 인증/인가 마일스톤의 downstream issue가 공유해야 하는 scope와 DAG (Directed Acyclic Graph) 기준을 고정한다. ADR-0011은 future generic contribution routing proposal이며, 현재 인증/인가 구현의 SSOT (Single Source of Truth)가 아니다.

현재 구현 기준은 이 문서와 GitHub milestone issue body다. 코드 작업 티켓은 이 문서를 기준으로 scope drift를 판단하고, 각 티켓의 수용 기준을 넘는 구현을 추가하지 않는다.

## 범위

현재 마일스톤은 다음을 포함한다.

- `core/spakky-auth` 신규 core package 등록
- `AuthContext`, `CredentialCarrier`, `AuthContextSnapshot`, decision/error model
- ABC + `abstractmethod` 기반 auth port와 `AuthCapability` enum
- decorator metadata와 sync/async AOP enforcement
- feature-local capability startup validation
- `spakky-cryptography`, `spakky-oidc`, `spakky-policy`, `spakky-openfga` provider plugin
- FastAPI, gRPC, Typer, task, Celery, event, RabbitMQ, Kafka, Saga boundary integration
- legacy security utility package shim 없는 제거와 migration documentation

## 범위 밖

다음은 현재 인증/인가 마일스톤에서 구현하지 않는다.

- generic multi-contribution routing engine
- provider priority/routing DSL (Domain-Specific Language)
- Redis auth persistence contribution
- SQLAlchemy auth persistence contribution
- audit log platform
- approval grant lifecycle
- MCP (Model Context Protocol) runtime/tool authorization
- authorized data/query filtering
- OIDC browser login/callback/session/refresh/logout route
- OpenFGA tuple/model admin 또는 list-resources API
- generic policy engine, policy UI/API

범위 밖 항목이 downstream issue에서 발견되면 현재 PR에 섞지 않고 follow-up issue로 분리한다.

## 핵심 결정

- decorator가 없는 boundary는 allow all이다.
- protected/decorated boundary는 fail closed다.
- auth failure decision state는 `ALLOW`, `CHALLENGE`, `DENY`, `ERROR`다.
- `AuthContext`는 `ApplicationContext` request/context scope에 저장된다.
- inbound adapter는 기존 `clear_context` 이후 사용자 handler/task/step 호출 전에 `AuthContext`를 seed한다.
- task, broker, event, saga 전파는 raw bearer token이 아니라 signed `AuthContextSnapshot`을 사용한다.
- framework 고정 어휘는 typed model 또는 `Enum`으로 정의한다.
- permission, role, scope, resource, action, claim, tenant 값은 string canonical ref로 둔다.
- public port는 ABC + `abstractmethod`를 사용하며 `Protocol`은 사용하지 않는다.
- auth capability provider 수가 0개 또는 2개 이상이면 feature-local startup validation에서 structured auth startup error로 실패한다.
- provider-specific priority/routing은 구현하지 않는다.

## Phase 3.5 Loop-3 결과

Phase 3.5 Loop-3는 `BLOCKING=false`, `CONFIDENCE=HIGH`로 통과했다. 이 baseline은 다음을 의미한다.

- DAG (Directed Acyclic Graph) 모순 0건
- 누락 blocker 0건
- 도달 불가능한 성공 기준 0건
- 표면적 매핑 0건
- scope drift 0건
- hard block 0건

Downstream issue는 아래 DAG 기준을 따른다. #278은 문서/spec 정합성 고정 작업이며, #279 이후 구현 티켓의 코드를 선행 구현하지 않는다.

## DAG 기준

```mermaid
graph TD
    A01["#278 A01: ADR and spec alignment"]
    A02["#279 A02: spakky-auth package registration"]
    A03["#280 A03: AuthContext and decision model"]
    A04["#281 A04: ABC ports and AuthCapability"]
    A05["#282 A05: decorators and AOP enforcement"]
    A06["#283 A06: capability startup validation"]

    P01["#284 P01: cryptography provider"]
    P02["#285 P02: OIDC bearer provider"]
    P03["#286 P03: policy evaluator provider"]
    P04["#287 P04: OpenFGA relation provider"]

    B01["#288 B01: FastAPI boundary"]
    B02["#289 B02: gRPC boundary"]
    B03["#290 B03: Typer boundary"]
    B04["#291 B04: task direct execution"]
    B05["#292 B05: Celery boundary"]
    B06["#293 B06: event snapshot propagation"]
    B07["#294 B07: RabbitMQ boundary"]
    B08["#295 B08: Kafka boundary"]
    B09["#296 B09: Saga boundary"]

    R01["#297 R01: security symbol mapping"]
    R02["#298 R02: remove legacy security package"]
    R04["#299 R04: final docs and migration guide"]
    R03["#300 R03: final conformance matrix"]

    A01 --> A02 --> A03 --> A04 --> A05 --> A06
    A04 --> P01
    A04 --> P02
    A04 --> P03
    A04 --> P04
    A05 --> B01
    A06 --> B01
    A05 --> B02
    A06 --> B02
    A05 --> B03
    A06 --> B03
    A05 --> B04
    A06 --> B04
    B04 --> B05
    P01 --> B05
    P01 --> B06
    B06 --> B07
    A05 --> B07
    A06 --> B07
    B06 --> B08
    A05 --> B08
    A06 --> B08
    A05 --> B09
    A06 --> B09
    P01 --> B09
    P01 --> R01
    P02 --> R01
    R01 --> R02
    P01 --> R02
    P02 --> R02
    P03 --> R02
    P04 --> R02
    R02 --> R04 --> R03
    P01 --> R03
    P02 --> R03
```

## Downstream issue body contract

The issue bodies for #279 through #300 are treated as the implementation contract for their own tickets. They must stay aligned with this baseline.

- #279 starts only after #278.
- #280 starts only after package registration in #279.
- #281 starts only after the semantic model in #280.
- #282 starts only after the public port/capability contract in #281.
- #283 validates auth feature capabilities locally; it does not implement generic contribution routing.
- Provider tickets #284 through #287 depend on the public auth contract in #281.
- Boundary tickets #288 through #296 depend on decorator/AOP enforcement and startup validation where their issue body lists #282 and #283.
- Removal/documentation tickets #297 through #300 run after provider and cleanup prerequisites listed in their issue bodies.

If a downstream ticket appears to require Redis/SQLAlchemy auth persistence, audit, approval, MCP runtime auth, data filtering, or generic provider routing, that requirement is out of scope for the current milestone unless a later issue explicitly accepts it.

## 검증

This document is documentation-only. The required verification for #278 is:

```bash
uv run mkdocs build --strict
```
