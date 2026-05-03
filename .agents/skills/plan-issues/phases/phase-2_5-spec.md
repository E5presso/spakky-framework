# Phase 2.5: 스펙 artifact 캡처 (Spec-Driven)

작업 전체의 **executable specification**을 캡처하여 사용자 의도를 손실 없이 고정한다. 이 artifact는 Phase 4에서 각 태스크 이슈의 본문에 **그대로 인용**되며, `/process-ticket`이 소비할 단일 진실 원천(SSOT (Single Source of Truth))이 된다.

## 본 단계의 SDD (Spec-Driven Development) 기조

스펙은 **재해석 여지가 없을 때까지 구체화**한다. 추상 불릿 한 줄로 요약 가능한 항목은 스펙이 아니라 슬로건이다. 다음 3가지를 강제한다:

1. **사용자 시나리오 우선 (User Stories first)** — 도메인/계약/규칙 진술 전에 "누가, 무엇을, 왜 관찰" 축을 먼저 고정한다. 기술 어휘로 시작하면 비즈니스 의도가 사라진다.
2. **모호함은 마커로 가시화 (`[NEEDS CLARIFICATION]`)** — 추론으로 채우지 않고 마커로 표시한다. 마커 1개라도 남으면 Phase 3 진입 차단.
3. **검증 가능성 (Given/When/Then + 측정 가능 SC (Success Criteria))** — 모든 acceptance scenario는 Given/When/Then으로, 모든 success criterion은 관찰 시점·관찰 대상·기대값을 포함한다.

## Grill-me Branch Sweep

Phase 0~2에서 유지한 Decision Branch Ledger를 스펙화 직전에 한 번 더 훑는다. 이 단계는 "사용자가 말한 요구를 정리"하는 단계가 아니라, 아직 결정되지 않은 설계 가지를 찾아 **한 번에 하나씩 닫는** 단계다.

### Branch별 처리 규칙

| Branch | 스펙 반영 위치 | 닫히지 않았을 때 |
|--------|----------------|------------------|
| architecture | §5 도메인 계약 / §8 상호작용 | `[NEEDS CLARIFICATION: 아키텍처 경계 ...]` |
| domain model | §4 FR / §5 도메인 계약 / §6 도메인 규칙 | `[NEEDS CLARIFICATION: 도메인 개념 ...]` |
| API contract | §5 도메인 계약 / §8 상호작용 | `[NEEDS CLARIFICATION: 계약 ...]` |
| data flow | §5 도메인 계약 / §7 경계 조건 / §8 상호작용 | `[NEEDS CLARIFICATION: 데이터 흐름 ...]` |
| UX-CLI surface | §3 사용자 시나리오 / §10 성공 기준 | `[NEEDS CLARIFICATION: 사용자 관찰면 ...]` |
| error policy | §7 경계 조건 / §10 성공 기준 | `[NEEDS CLARIFICATION: 오류 정책 ...]` |
| compatibility | §2 가정 / §9 범위 밖 | `[NEEDS CLARIFICATION: 호환성 ...]` |
| rollout | §2 가정 / §9 범위 밖 / §10 성공 기준 | `[NEEDS CLARIFICATION: 배포·마이그레이션 ...]` |
| tests-docs | §10 성공 기준 / §11 검증 체크리스트 | `[NEEDS CLARIFICATION: 검증·문서 ...]` |

### 사용자 질문 규칙

ledger에 open branch가 있으면 사용자에게 질문하기 전에 코드·문서·기존 이슈로 답할 수 있는지 먼저 확인한다. 그래도 남는 질문은 아래 형식으로 하나씩 제시한다.

```
질문: {현재 가장 upstream인 미해결 결정}
왜 묻는가: {막고 있는 FR/SC/태스크}
권장 답안: {코드베이스 근거 기반 선택}
대안: {있다면 1-2개와 비용}
```

사용자 답변은 ledger와 스펙 양쪽에 반영한다. ledger만 닫고 스펙 본문에 반영하지 않으면 Phase 3 진입 금지.

## 규모별 분기 (Phase 2 판정 결과에 따라)

### 에픽 규모 (새 마일스톤)

마일스톤 수준에서 **공용 스펙 문서**를 작성한다 (아래 "스펙 artifact 구조" 그대로). 자식 티켓은 공용 스펙을 §번호로 참조하고 자기 범위만 추가 서술한다 — 같은 스펙을 자식마다 복제하면 용어·계약이 엇갈린다.

저장 위치: **GitHub 마일스톤 description**. Phase 4에서 그대로 주입.

### 그룹·단일 규모

스펙 artifact 한 건을 작성한다. 단일 규모이면 §3.1 (User Stories) 1개만, §4 (FR (Functional Requirement)) 3-5개로 압축할 수 있다. 섹션은 삭제 금지 — "해당 없음" 명시.

## 스펙 artifact 구조

### §1. 비즈니스 의도 (1-2 문단)

**누가 어떤 문제로 막혀 있고, 이 작업이 끝나면 무엇이 바뀌는지**를 사용자/운영 어휘로 서술. 기술 용어(Aggregate/Port/Repository/UseCase/Aspect/Plugin)로 의도를 대체하면 자기 반려.

> 작성 후 자기 검증: 이 문단을 product manager가 읽고 "왜 이 작업이 필요한가"에 답할 수 있는가? 못 하면 재작성.

### §2. 가정 (Assumptions)

이 스펙이 의존하는 컨텍스트·전제. 명시하지 않으면 "당연하다"는 가정으로 silent drift 발생.

- **사용자 컨텍스트**: 누가, 어떤 빈도로, 어떤 도구로 사용하는가
- **데이터/환경 가정**: 입력 데이터의 양·형태·정합성 가정, 인프라 가정
- **시스템 의존**: 다른 패키지/Bounded Context·서비스·외부 API 가정
- **범위 가정**: tenancy, locale, 권한 등에 대한 가정

각 가정은 **명시적 진술**로. 모호하면 `[NEEDS CLARIFICATION: 질문]`.

Phase 0~2의 질문에서 사용자가 승인한 권장 답안은 여기 또는 §5~§9에 명시한다. "대화에서 합의됨"으로 남기지 않는다.

### §3. 사용자 시나리오 (User Stories)

각 user story는 다음 형식:

```
### US-N (P{1|2|3}) — {짧은 제목}

**Story**: As a {actor}, I {capability}, so that {outcome}.

**Why this priority**: {왜 P1/P2/P3인지 — 비즈니스 가치·차단 관계·MVP 정의}

**Independent Test**: {이 story 단독으로 관찰 가능한 결과 1줄. 다른 story 완료 없이 검증 가능해야 함}

**Acceptance Scenarios**:

- **Scenario 1**: Given {초기 상태}, When {액션}, Then {관찰 가능한 결과}.
- **Scenario 2**: Given ..., When ..., Then ...
- **Edge — {엣지 케이스 이름}**: Given ..., When ..., Then ...
```

**규칙**:
- P1은 MVP (Minimum Viable Product) 필수, P2는 차단 없는 확장, P3는 nice-to-have.
- 단일 규모는 US (User Story) 1개로 충분. 에픽도 P1은 1-3개로 제한 (16 AC 부풀리기 금지 — Kiro 안티패턴).
- 모든 Scenario는 Given/When/Then을 명시적으로 포함. "올바르게 동작" 같은 추상 결과 금지.
- Edge case는 일반 Scenario와 같은 형식. "예외 처리" 추상화 금지.

### §4. 기능 요구사항 (Functional Requirements)

번호가 매겨진 단일 기능 진술 목록. 각 FR (Functional Requirement)은 **검증 가능한 단일 명제**.

```
- **FR-001**: 시스템은 {조건}일 때 {관찰 가능한 행동}을 한다.
- **FR-002**: 시스템은 {입력}을 받아 {출력}을 반환한다 (단, {제약}).
- **FR-003**: [NEEDS CLARIFICATION: {모호한 지점에 대한 질문}]
```

**규칙**:
- 한 FR (Functional Requirement) = 한 명제. AND/OR로 묶지 말 것.
- 도메인 어휘(`AGENTS.md` "프로젝트 특수 컨벤션", `ARCHITECTURE.md` 도메인 모델)만 사용. 기술 용어는 §5.도메인 계약에서.
- 측정 불가능하거나 검증 불가능하면 SC (Success Criteria)로 옮기거나 재작성.
- 모호한 지점은 추론으로 메우지 말고 `[NEEDS CLARIFICATION: ...]`로 표시.

### §5. 도메인 계약 (Domain Contract)

이 기능이 소비/제공하는 입출력의 **의미 수준 계약**. API 시그니처가 아니라 **사전조건·사후조건·불변식·상태 전이**.

- **입력**: 타입 + 필드 의미 + 유효 범위 + 정합성 가정
- **출력**: 타입 + 필드 의미 + 가능한 상태 + 관찰 가능 시점
- **사전조건 (Preconditions)**: 호출자가 보장해야 할 조건
- **사후조건 (Postconditions)**: 시스템이 보장하는 결과 상태
- **불변식 (Invariants)**: 작업 전후로 유지되는 조건
- **상태 전이 (State Transitions)**: 상태 머신이 있으면 다이어그램 또는 표

> **금지**: `HealthCheckController.check() -> HealthStatus` 같은 시그니처. **허용**: "HealthCheck는 등록된 Probe 0~N개의 결과를 집계한다 (N은 Container에서 Probe 인터페이스 구현체 수). 한 Probe라도 unhealthy면 전체 unhealthy."

### §6. 도메인 규칙 (Business Rules)

§5에 들어가지 않는 **비즈니스 불변식·정책·계산 규칙**. FR (Functional Requirement)이 "무엇을 한다"라면 도메인 규칙은 "어떤 진실이 항상 성립한다".

예: "AggregateRoot 1개당 도메인 이벤트 N개는 트랜잭션 커밋 시점에만 발행", "OutboxRelay는 처리 실패 시 멱등 재시도", "Saga 보상 트랜잭션은 역순으로 실행".

### §7. 경계 조건 / Edge Cases

정상 흐름 외 **경계·예외·동시성·재시도** 규칙. §3 Acceptance Scenarios의 Edge와 다른 점은 여기는 **runtime 정책**, 거기는 **관찰 가능한 시나리오**.

- 입력이 0/empty/null일 때
- 동시 수정·중복 호출
- 외부 의존 실패 시 (재시도 정책·circuit breaker·fallback)
- timeout·rate limit

### §8. 상호작용 (Integration Surface)

다른 도메인/서비스/이벤트와의 관계.

- 소비하는 이벤트/API: 이벤트 이름 + 페이로드 의미 + ordering·at-least-once 가정
- 발행하는 이벤트/API: 이벤트 이름 + 페이로드 의미 + 발행 시점 + 멱등성
- 외부 의존: DB (Database)·메시징·외부 서비스의 어떤 보장에 의존하는가

### §9. 범위 밖 (Out of Scope) — Non-goals

**의도적으로 배제하는 항목**을 명시. 모호함을 감지한 사용자가 "그것도 해 주세요"로 stretch하지 못하게.

- "이번 작업은 multi-tenancy 고려하지 않음"
- "retry 전략은 후속 티켓 #XXX"
- "성능 최적화는 본 마일스톤 범위 밖"

### §10. 성공 기준 (Success Criteria)

번호가 매겨진 **측정 가능한 결과 목록**. 각 SC (Success Criteria)는 (관찰 시점, 관찰 대상, 기대값) 3요소 포함.

```
- **SC-001**: 마일스톤 종료 시점에 {관찰 대상}이 {기대값}을 달성한다.
- **SC-002**: {지표}가 기준 X 이상/이하로 측정된다 (관찰 도구: {도구}).
- **SC-003**: {정성 기준}이 운영팀 검수에서 통과한다.
```

**규칙**:
- "잘 동작한다", "사용자가 만족한다" 같은 추상 표현 금지.
- 정성 기준이 불가피하면 **관찰자와 검수 절차**를 명시.
- FR (Functional Requirement)과 1:1 대응이 아니어도 됨. SC (Success Criteria)는 사용자 가치 관점, FR은 기능 명세 관점.


### §11. 검증 체크리스트 (Spec Self-Review)

스펙 작성을 끝낸 직후 **에이전트가 스스로 통과시키는 게이트**. 하나라도 실패면 사용자 제시 전에 보강. 자기 판정의 self-confirmation bias는 Phase 3.5 외부 게이트로 회수되므로 본 셀프 체크는 **최대한 적대적으로** 수행한다 (스스로 "이 정도면 됐다"가 보이면 항목 추가 검출 신호).

- [ ] §1 비즈니스 의도가 PM 어휘로 작성되었는가 (기술 용어로 의도 대체 없음)
- [ ] 모든 US (User Story)가 Given/When/Then으로 검증 가능한 시나리오를 가지는가
- [ ] 모든 US가 단독으로 테스트 가능한 Independent Test를 가지는가
- [ ] 모든 FR (Functional Requirement)이 단일 명제이며 검증 가능한가
- [ ] 도메인 어휘가 도메인 사전(`AGENTS.md` "프로젝트 특수 컨벤션", `ARCHITECTURE.md` 도메인 모델 섹션)과 일치하는가 (신규 어휘는 사전 등록 절차 거쳤는가)
- [ ] **요청 어휘 4축 정합 (charter §4-A)** — 본문에 등장한 모든 핵심 어휘가 (a) 사용자 입력 본문, (b) 도메인 사전, (c) 패키지 `README.md`/`docs/`, (d) 코드베이스 — 4축에서 등가로 사용되는가. 한 축이라도 어긋나면 `[NEEDS CLARIFICATION: 어휘 X — 출처별 의미 차이 확인]` 마커.
- [ ] **Decision Branch Ledger 반영** — architecture / domain model / API contract / data flow / UX-CLI surface / error policy / compatibility / rollout / tests-docs branch가 모두 `RESOLVED`이거나, §2/§5/§7/§8/§9/§10에 명시적으로 반영되었거나, `[NEEDS CLARIFICATION]`으로 남아 Phase 3을 차단하는가.
- [ ] **질문 근거 검증** — 사용자에게 물은 질문 중 코드·문서·기존 이슈 탐색으로 답할 수 있었던 것이 없는가. 있었다면 질문을 취소하고 탐색 근거로 스펙을 갱신했는가.
- [ ] **권장 답안 추적** — 질문마다 제시한 권장 답안이 사용자 승인/수정/거절 중 어떤 상태인지 ledger에 남아 있고, 승인된 답안만 스펙에 반영되었는가.
- [ ] §5 도메인 계약에 사전·사후조건·불변식이 명시되었는가
- [ ] §9 범위 밖이 의도적 비목표로 명시되었는가 (`해당 없음`이 실제 부재인지 검토 부재인지 구분)
- [ ] §10 SC (Success Criteria)가 모두 (관찰 시점, 관찰 대상, 기대값) 3요소를 포함하는가
- [ ] **`[NEEDS CLARIFICATION: ...]` 마커가 0개인가** — 1개라도 남으면 Phase 3 진입 차단
- [ ] **Silent assumption 자가 검출** — 스펙 본문에서 사용자 입력에 등장하지 않은 핵심 어휘·전제·기본값을 모두 식별. 식별된 항목은 모두 `[NEEDS CLARIFICATION]`으로 마킹하거나 §2 가정에 명시. 추론으로 메우면 안 됨.

## Constitution Check (charter 게이트)

스펙이 `charter.md`의 원칙(정책 → 비즈니스 → 코드 위계 / 7차원 품질 바 / 외부 게이트 / 모호함 단계별 강도 / 토큰=비용)과 충돌하는지 확인.

| 원칙 | 검증 항목 |
|------|-----------|
| §1 정책 → 비즈니스 → 코드 | 기술 용어가 비즈니스 의도를 대체하지 않았는가 |
| §3 7차원 품질 바 (간결성·자기설명성) | FR (Functional Requirement) / SC (Success Criteria)가 한 명제 단위인가 (AND/OR로 묶이면 분리) |
| §3 7차원 품질 바 (자기설명성) | "정리/개선/최적화/유연성" 같은 모호어가 스펙 본문에 없는가, 번호+일반명사 라벨 없는가 |
| §5 모호함 처리 | `[NEEDS CLARIFICATION]` 마커가 모두 해소되었는가 |

위반 시 **Complexity Tracking** 표를 artifact에 추가:

| 위반 항목 | 왜 필요한가 | 더 단순한 대안을 거부한 이유 |
|-----------|-------------|-------------------------------|
| {원칙 § 번호} | {비즈니스 이유} | {대안 + 거부 근거} |

위반이 정당화되지 않으면 스펙을 재작성한다. Complexity Tracking은 **사용자 명시 승인** 없이 통과시키지 않는다.

## 작성 원칙 (요약)

- **구체성 > 분량**: Tessl 경험 — "스펙을 더 구체화할수록 코드 생성의 반복성이 증가". 추상적인 5페이지보다 구체적인 1페이지.
- **구현 디테일 배제**: 파일 경로, 함수 시그니처, 데이터 스키마 JSON은 §5에서도 금지. 의미 수준만.
- **추상 스펙은 꼼꼼히**: 도메인 개념·규칙·계약·경계는 최대한 상세하게. 빈틈은 `/process-ticket` 할루시네이션의 진입 경로.
- **모호함은 추론 금지**: `[NEEDS CLARIFICATION: ...]` 마커로 가시화 → Phase 2.5 내에서 해소.

## 스펙 승인

§11 self-review를 통과한 스펙 artifact 전체를 사용자에게 제시한다. 제시 본문 상단 2줄에 "이 스펙이 사용자/운영에게 가져오는 변화"를 자기 문장으로 재진술한다 (artifact 원문 인용 금지 — 재진술이 목적 어휘로 가능하지 않으면 Phase 2-0으로 복귀 신호).

`AskUserQuestion` 옵션:
- **승인**: 이 스펙으로 Phase 3(분해) 진행
- **CLARIFICATION 응답**: 마커 질문에 답변 → 스펙 갱신 후 재제시
- **스펙 수정**: 특정 섹션 수정 (notes에 기재)
- **재논의**: Phase 2부터 재시작

> 승인 후 Phase 3/4에서 스펙을 수정하지 않는다. 수정이 필요하면 Phase 2.5로 복귀.

## 자명한 티켓 — 스펙 승인 생략 조건

아래 조건을 **모두** 만족하면 스펙 artifact를 내부적으로 작성만 하고 승인을 생략한다 (over-specification 회피):

1. 단일 구조 (이슈 1개로 완결)
2. 단일 패키지
3. 도메인 규칙/경계/상호작용이 사용자 입력에서 직접 도출 (추가 설계 판단 없음)
4. **`[NEEDS CLARIFICATION]` 마커 0개** — 마커가 있으면 자명하지 않음

자명 생략 시에도 §1 비즈니스 의도, §3 US (User Story) 1개 (Given/When/Then 1-2 scenario), §4 FR (Functional Requirement) 1-3개, §10 SC (Success Criteria) 1-2개는 작성한다 — Phase 4 self-check에서 검증되므로 누락 시 차단된다.

그 외에는 승인을 반드시 받는다.
