---
name: audit-spec
description: GitHub 마일스톤·프로젝트 또는 이슈 묶음을 받아 모호·정합 모순·정책 위반을 식별하고 우선순위 순으로 정정 PR을 위임합니다. 코드 변경 없이 스펙 본문만 다룹니다.
argument-hint: "<마일스톤 ID/이름/URL 또는 이슈 번호 묶음>"
user-invocable: true
---

# Audit Spec — 마일스톤/이슈 본문 모순 감사 + 정정 위임

마일스톤 description, 부모 이슈, 자식 이슈의 본문 사이에 누적된 모호함·stale 표기·정책 위반·blocker 모순을 식별하고, 우선순위 순으로 서브에이전트에 정정 위임을 자동화한다. **코드 변경 없음 — GitHub Issue 본문만 다룬다.**

## 본질

`/plan-issues`가 만든 스펙은 작성 시점에는 정합하지만, 후속 Wave가 진행되며 **이전 Wave 결과**(Done 이슈 산출물, Cancel 결정, 정책 변경)가 누적되면서 자식 이슈 본문이 stale해진다. 본 스킬은 그 누적 격차를 외부 게이트로 회수한다.

charter §1 적용: 본 스킬은 *비즈니스 의도 → 기술 결정* 위계를 검증하지 않는다 (그건 `/plan-issues`의 책임). 본 스킬은 **스펙 본문 ↔ 본문, 본문 ↔ 코드 사실, 본문 ↔ 정책 SSOT** 사이 정합만 본다.

## 사용법

```
/audit-spec Agentic Hexagonal: Graph를 UseCase 동격 orchestrator로 승격
/audit-spec https://github.com/E5presso/spakky-framework/milestone/12
/audit-spec #128, #129, #130 (이슈 묶음)
```

인자: 마일스톤 식별자(이름·번호·URL) 또는 쉼표로 구분된 이슈 번호 묶음.

## 핵심 원칙

1. **활성 이슈만 감사**: Closed(완료) · Closed(취소) · Duplicate은 결과 보고에서 제외하되, "이미 Closed지만 description이 Backlog로 표기된" stale 메타데이터는 별도 항목으로 보고.
2. **결과 명제 ≠ 검증 수단**: 자식 이슈 수용 기준이 별도 CI / PR 본문 첨부 / 리뷰어 수동 확인 같은 **검증 수단을 강제**하면 정책 위반 후보. 코딩 컨벤션은 `.agents/rules/charter.md`, `.agents/rules/behavioral-guidelines.md`, `docs/adr/0009-agentic-hexagonal-architecture.md`가 default 차단점.
3. **추상 인터페이스 표기 stale**: 이전 Wave에서 `I*` 추상 인터페이스(Port)가 제거된 경우, 이후 Wave 본문에서 같은 식별자를 사용하면 stale. P2 같은 "추상 → 구체 전환" Wave 직후가 위험 구간.
4. **사용자 질의 ≠ 자율 진행** (charter §4):
   - **사용자 질의 (paranoid)**: 정책 결정 (사전 등재 시점·새 마이크로 이슈 신설), 도메인 사전 미등재 신규 어휘, 마일스톤 §4.4 외부 계약 변경 가능성.
   - **자율 진행 (positive bias)**: stale 표기 정정, priority 격상, blocker chain 정정, 수용 기준 escape hatch 약화.
5. **추가 모순점 후속 처리**: 정정 위임 도중 새로 발견된 모순은 **이 세션 내에서** 후속 TODO로 처리. 다음 세션 위임 금지 (`.agents/rules/behavioral-guidelines.md` "Surgical Changes" 컨텍스트 윈도우 관리).
6. **Self-confirmation bias 회피 (fresh slate 재감사)**: Phase 4 정정 위임 후 Phase 6 수렴 루프로 재진입할 때, 재감사 서브에이전트에는 **이전 회차 수정 내역·발견 목록을 전달하지 않는다.** 변경된 부분에만 attention이 가서 누적/유발 모순을 놓치는 간접적 self-confirmation bias를 차단하기 위함이다. 재감사 prompt는 "본문을 처음 보는 시각으로 8축 검사" 명령만 포함한다.

## Phase 0: 입력 수집

`$ARGUMENTS`에서 다음을 추출:
- 마일스톤 번호 / 이름 / URL: `gh api repos/E5presso/spakky-framework/milestones`로 정규화
- 또는 이슈 번호 묶음: 각 `gh issue view <번호> --json number,title,body,labels,milestone,state,assignees`

식별자 모호 시 `AskUserQuestion`으로 객관식 질의.

## Phase 1: 활성 이슈 수집

1. `gh api repos/E5presso/spakky-framework/milestones/<번호>`로 마일스톤 description 확보 (대형이면 큰 부분 발췌 보존).
2. 마일스톤 description의 §"커버리지 매핑" / §"기존 이슈 처리" 표를 읽어 **명시된 활성 이슈** + Closed 분류 1차 파악.
3. **자식 fetch는 컨텍스트 보호 위해 서브에이전트에 위임**: 부모 이슈들에서 도출한 자식 번호 목록을 `general-purpose` 서브에이전트로 보내 일괄 조회 + 1차 분류.
4. 마일스톤이 명시 안 한 자식이 부모 본문에 등장하면 → 마일스톤 description 갭 후보 (Phase 2 항목).

## Phase 2: 감사 (8축)

각 활성 이슈 본문을 다음 8축으로 검사:

| 축 | 검사 |
|----|------|
| 1. 이전 Wave 산출물 ↔ 자식 본문 stale | 제거·변경된 Port/클래스/메서드 식별자 잔존, 정정 매핑 가능 여부 |
| 2. 검증 수단 강제 표기 | 별도 CI, PR 첨부, 리뷰어 수동 확인 등 수단 강제. 수용 기준은 결과 명제만 둔다 |
| 3. 외부 계약 위반 가능성 | REST/API, 이벤트 스키마, DB 스키마, 인덱스, Audit Log, 외부 계약 화이트리스트 누락 |
| 4. 도메인 사전 미등재 신규 어휘 | `ARCHITECTURE.md` / `AGENTS.md` 미등재 어휘, 사전 등재 시점 모순 |
| 5. Blocker / 의존 chain 모순 | blocker 전무, GraphQL ↔ 본문 불일치, Sub-issue 누락, 부모/자식 chain 충돌, transitive blocker, priority ↔ 차단 게이트 부정합 |
| 6. 수용 기준 모호 | escape hatch, "또는", "약 N개", 결정 미루기 표현 |
| 7. 마일스톤 description ↔ 자식 이슈 | 커버리지 매핑 누락, Closed/Backlog stale, description chain ↔ blockedBy 불일치 |
| 8. 본문 ↔ 도메인 사전 ↔ 코드 사실 | 클래스·메서드·호출 경계가 실제 코드와 도메인 사전에 존재하는지 |

## Phase 3: 심각도 분류 + 사용자 보고

각 발견을 4단계로 분류:

| 심각도 | 정의 | 처리 |
| -- | -- | -- |
| **Critical** | Wave 진입 차단 또는 정책 위반 위험 | 자율 정정 위임. 정책 결정 필요시 사용자 질의. |
| **High** | Silent assumption 유발 | 자율 정정 위임. 정책 결정 필요시 사용자 질의. |
| **Medium** | 수용 기준 모호로 검증 실패 위험 | 자율 정정 위임. |
| **Low** | 스타일·일관성 | 자율 정정 위임. |

Critical 예시:
- 다티켓 마일스톤의 모든 활성 자식 `blockedBy`가 비어 있음
- Phase 3 DAG에 edge가 있는데 GitHub `addBlockedBy` 관계 또는 본문 `## 선행 이슈`가 누락됨
- blocker cycle 또는 완료 불가능한 blocker chain

보고 형식:
```
## N. <심각도> — <짧은 제목>
- 위치: <이슈 번호> §"<절>" 또는 수용 기준 N번
- 문제: <구체적 모호함/오류>
- 영향: <어떤 후속 작업이 어떻게 어긋날지>
- 제안: <어떻게 고치면 되는지>
```

마지막에 "권고 처리 순서"로 우선순위 그룹화.

## Phase 4: 우선순위 순 정정 위임

각 그룹별로 별도 서브에이전트(opus 권장)에 위임. **검증 수단 강제 표기 추가 금지** 원칙은 모든 위임 prompt에 명시.

### 위임 prompt 골격

필수 입력: 대상 이슈 번호, 모순 사유 + 정책 SSOT, 정정 매핑 표, read-back 요구. 제약: description 외 필드 변경 금지(명시 항목 제외), 기존 톤 유지, `.agents/rules/behavioral-guidelines.md` 축약어 풀이, 검증 수단 표기 추가 금지. 보고는 이슈별 변경 요약 1줄 + 추가 발견 모순점(보고만).

### 사용자 질의 항목 (정책 결정)

- 새 이슈 신설이 필요한 항목 (예: "사전 prospective 등재 마이크로 이슈") — `AskUserQuestion`으로 옵션 제시 (default 권장 옵션 첫 번째).
- 마일스톤 §4.4 외부 계약 변경 가능성이 있는 항목.
- 도메인 사전 미등재 신규 어휘.

자율 진행 항목은 charter §4-B default ("프로페셔널 완벽주의자 선택") 적용.

## Phase 5: 추가 모순점 후속 TODO

각 위임 결과 보고에서 "추가 발견 모순점" 항목을 받아 본 세션 TODO에 추가. 위임된 작업 범위 외이지만 같은 세션에서 처리. 다음 세션 위임 금지.

## Phase 6: 수렴 루프

Phase 4 정정 위임이 완료되면 GitHub Issue 본문이 갱신된 상태에서 **Phase 1~5를 fresh slate로 재진입**하여 누적/유발 모순을 회수한다. 작성 시점의 self-confirmation bias로 1회차 감사가 놓친 항목을 외부 게이트로 회수하기 위함이다.

### 수렴 루프 절차

1. Phase 4 자율 정정 위임 완료를 확인한다 (백그라운드 서브에이전트면 알림 수신까지 대기).
2. **재감사 서브에이전트 호출** — 핵심 원칙 6 "fresh slate 재감사" 적용. 위임 prompt에 다음을 포함하지 않는다:
   - 이전 회차 발견 목록
   - 이전 회차 정정 내역 (어느 이슈 본문이 어떻게 바뀌었는지)
   - "이미 정정되었을 것"이라는 가정
3. 재감사 결과 수신 후 종료 분기:
   - **Critical 0개로 수렴** → Phase 7 진입.
   - **Critical 0 + High/Medium/Low만 잔존** → 자율 정정 가능 항목은 Phase 4로 위임, 사용자 질의 항목은 `AskUserQuestion`으로 질의. 질의 회신 후 본 루프 1회 추가 진입.
   - **Critical 잔존** → Phase 4로 자율 정정 위임 (정책 결정 필요시 사용자 질의) 후 본 루프 1회 추가 진입.
4. **수렴 실패 가드**: 동일 발견이 연속 2회 잔존 또는 누적 iteration 3회 도달 시 사용자 보고 후 종료. 무한 루프 차단.

### 재감사 위임 prompt 골격

마일스톤/활성 자식 본문을 처음 보는 시각으로 8축 감사한다. 이전 발견·수정 이력·"이미 정정" 가정을 전달하지 않는다. Critical 0개면 그 사실을 명시하고 거짓 발견을 만들지 않는다.

## Phase 7: 최종 보고

수렴 또는 사용자 회신 대기 시점에서 다음을 1회 보고한다:
- 누적 정정 항목 (이슈 번호 + 1줄 요약 list)
- 미해소 항목 (있으면 사유)
- iteration 수
- 최종 산출물 링크 (정정된 이슈 URL 묶음 또는 마일스톤 URL)

처리 종료 조건: 모든 식별 모순점이 정정됐거나 사용자 질의 회신을 받았을 때.

## 제약 사항

- **코드 변경 없음** — 본 스킬은 GitHub Issue 본문만 다룬다. 코드 정합 검증 결과로 코드 변경이 필요하면 후속 이슈를 `/plan-issues`로 생성.
- **마일스톤 description 갱신은 신중히** — 본문이 매우 길고 markdown 표·mermaid 다이어그램 포함. 부분 치환 시 다른 절 절단 검증 필수.
- **"이왕 하는 김에" 금지** (`.agents/rules/behavioral-guidelines.md` §3): 감사 결과 외 인접 본문 개선 금지.
- **하네스 수정 동반 시** — 본 스킬 사용 결과로 하네스 보강이 필요하면 `.agents/rules/harness-writing.md`와 `.agents/skills/process-ticket/phases/phase-2-plan.md`의 하네스 교정 절차를 따른다.

## 참고 컨텍스트

- `.agents/rules/charter.md` §1 (정책 → 비즈니스 → 코드) + §4 (모호함 처리)
- `.agents/rules/behavioral-guidelines.md` §3 "Surgical Changes" + "스펙 검증" + "네이밍"
- `.agents/rules/harness-writing.md` (보편 원리만 작성)
- `/plan-issues` (스펙 작성 측 짝)
- `/refactor-code` (코드 측 감사 짝 — 본 스킬은 스펙 측)
