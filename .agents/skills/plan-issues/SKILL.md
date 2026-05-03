---
name: plan-issues
description: 자연어 기능 방향성을 받아 마일스톤/태스크/서브태스크 3단 위계의 GitHub 이슈를 자동 생성합니다.
argument-hint: "<기능 방향성 설명>"
user-invocable: true
---

# Plan Issues — 기능 기획 → GitHub 이슈 자동 생성

자연어로 설명된 기능 방향성을 받아, 에이전트(`/process-ticket`)가 소비할 수 있는 구체적인 GitHub 이슈 티켓을 자동 생성한다. Spec-first 워크플로로 스펙·분해 artifact를 먼저 확정하고 이슈 본문은 기계적으로 주입한다.

## 비즈니스 의도 우선 (Paranoid Posture)

본 스킬은 charter §4-A에 따라 **편집증 수준의 paranoid posture**로 동작한다. 이 단계의 산출물(스펙·분해 artifact)은 후속 모든 작업의 SSOT (Single Source of Truth)이 되며, 여기서 발생한 모호함은 `/process-ticket`이 silent assumption으로 메우게 된다 — 결과적으로 코드 품질 + 생산성 손실로 직결된다.

따라서:
- **모호함 자판정 금지의 강도가 최대치**다. "이 정도면 알 수 있겠지", "기본값으로 진행", "본문 추론으로 메우기" 등의 패턴을 모두 차단한다.
- **요청 어휘 4축 정합 검증**: 요청 어휘가 (a) 사용자 입력 본문, (b) 도메인 사전(`AGENTS.md` "프로젝트 특수 컨벤션", `ARCHITECTURE.md` 도메인 모델 섹션), (c) 패키지 `README.md` / `docs/`, (d) 코드베이스 — 4축 모두에서 등가로 사용되는지 확인. 한 축이라도 어긋남이 발견되면 즉시 사용자 질의.
- **집요한 후속 질문**: 한 번 답을 얻었더라도 그 답이 또 다른 공백을 드러내면 그것도 묻는다. "한 번 물었으니 충분"으로 종결하지 않는다.
- **외부 게이트 우선**: Phase 3.5 시뮬레이션 게이트는 self-confirmation bias 회피의 핵심 장치 — 비용 절감 사유로 생략하지 않는다 (자명 티켓 조건 충족 시에만 생략).

`charter.md` §1·§2를 모든 Phase 전체에 선행 적용한다. Phase 2(위계 판정) 진입 전, charter §2 3-축 정렬(마일스톤 의도 / 티켓 위치 / 도메인 사전 정합)을 목적 어휘로 스스로 답하고 사용자에게 2-3줄로 요약 공유한다. 하나라도 막히면 Phase 2 진입 금지.

## 핵심 설계 — Spec-Driven Development (SDD) 워크플로

본 스킬은 GitHub Spec Kit / Kiro / Tessl 같은 SDD (Spec-Driven Development) 도구의 핵심 패턴을 차용하되, GitHub Issues 티켓 + `/process-ticket` 소비 형태로 적응한다.

### 핵심 SDD 원칙 (스펙 품질 = 구현 품질)

1. **사용자 시나리오 우선 (User Stories first)**: 도메인/계약/규칙 진술 전에 "누가, 무엇을, 왜 관찰" 축을 먼저 고정한다. 모든 acceptance scenario는 **Given/When/Then**으로.
2. **모호함은 마커로 가시화 (`[NEEDS CLARIFICATION]`)**: 추론으로 메우지 않고 마커로 표시한다. 마커 1개라도 남으면 Phase 3 진입 차단.
3. **번호 추적 (FR-/SC- IDs)**: 모든 기능 요구사항(FR (Functional Requirement))과 성공 기준(SC (Success Criteria))에 ID를 부여하여 태스크 → 요구사항 양방향 traceability 확보.
4. **검증 가능한 SC**: 모든 성공 기준은 (관찰 시점, 관찰 대상, 기대값) 3요소 포함. "잘 동작한다" 금지.
5. **Constitution Check**: `charter.md` 위반은 Complexity Tracking 표로 가시화 후 사용자 승인 없이 통과 금지.
6. **스펙 self-review gate**: Phase 2.5 §11 체크리스트를 에이전트가 자체 통과시킨 후에만 사용자 제시.

### Phase 흐름

1. **Phase 2.5** — 11섹션 구조의 **executable specification artifact**를 캡처한다 (비즈니스 의도·가정·US (User Story)·FR (Functional Requirement)·도메인 계약·도메인 규칙·경계·상호작용·범위 밖·SC (Success Criteria)·self-review).
2. **Phase 3** — 스펙을 만족하는 태스크 분해 + 쓰기 충돌 매트릭스 + 레이어 선후 + **FR/SC 커버리지 매핑** + 부모 의존 상속.
3. **Phase 3.5** — 서브에이전트 시뮬레이션 게이트 (T1 티켓별 cold reading + T2 DAG (Directed Acyclic Graph) 모순 + T3 SC value drift). Soft block으로 검토 후보 사용자 일괄 결정.
4. **Phase 4** — 확정된 artifact를 템플릿 슬롯에 **기계적으로 주입**. self-check 11항목 (마커 0개 / FR-SC 역참조 / US 본문 인용 / Constitution 등) + Phase 3.5 게이트 통과 확인 후 이슈 생성.

이 구조는 "논의 내용과 본문 불일치" / "스펙 부실 → `/process-ticket` 할루시네이션" / "의존관계 오류" / "사용자 의도 손실"을 구조적으로 방지한다.

### 과대 설계 회피 (Kiro 안티패턴 회피)

- 자명 티켓(단일 + 단일 패키지 + 직접 도출 + 마커 0)은 Phase 2.5/3 승인 생략.
- 단일 규모는 US (User Story) 1개, FR (Functional Requirement) 1-3개로 압축 가능. **11섹션을 모든 규모에 채우는 것이 목적이 아니다 — 의도 손실을 막는 것이 목적**.
- "버그 1건을 16 AC로 부풀리기" 안티패턴: P1은 1-3개로 제한.

## 사용법

```
/plan-issues 프레임워크에 헬스체크 엔드포인트를 추가하고 싶어
```

인자: 기능 방향성 설명 (자연어)

## 상수

| 항목 | 값 |
|------|-----|
| GitHub 프로젝트 | `Spakky Roadmap` |
| 기본 브랜치 | `develop` |

> **GitHub 마일스톤은 상수가 아니다.** 이번 기능이 어느 마일스톤에 속하는지(또는 신규 마일스톤이 필요한지)는 Phase 0/1에서 사용자와 합의하여 세션 변수로 고정한다 (Phase 1·2·4가 모두 이 변수를 공유). 하드코딩 / 메모리에 저장된 기본값에 의존하지 않는다 — `write-skill.md` "특정 사용자 login, 프로젝트 ID 등을 하드코딩하지 않는다" 원칙과 일관.

---

## Phase 개요

각 Phase 진입 시 해당 파일을 Read로 로드하여 단계별 절차를 적용한다.

## Phase 0: 입력 수집

1. `$ARGUMENTS`에서 기능 방향성을 수집한다.
2. 입력이 모호하거나 불충분하면 `AskUserQuestion`으로 보강한다 (목표 / 범위 / 제약 3축).
3. 입력이 충분히 명확하면 Phase 1로 진행한다.

## Phase 1: 코드베이스 & 기존 마일스톤 분석

**Explore 서브에이전트**로 현재 코드베이스를 분석한다.

1. `ARCHITECTURE.md`, `CONTRIBUTING.md`, `AGENTS.md` 읽기
2. 의존성 그래프에서 영향받는 패키지 식별 (`core/*`, `plugins/*`)
3. 기존 유사 패턴 탐색 (참조할 수 있는 기존 구현 파악)
4. `docs/adr/` 디렉토리에서 관련 ADR 존재 여부 확인
5. 영향 패키지별 현재 공개 인터페이스(ABC 기반 인터페이스) 파악
6. `gh issue list --milestone <name>` / `gh api repos/{owner}/{repo}/milestones`로 기존 마일스톤 조회 — 범위 겹침 확인
7. **산출물 중복 검사 게이트**: 분해가 만들어낼 산출물(파일·공개 함수·클래스·이벤트·매퍼 이름)이 코드베이스 또는 동일 프로젝트의 `closed` 자식 이슈에 이미 존재하면 Phase 2-0으로 복귀하여 사용자 판정(취소/범위 축소/사유 명시 후 신설). forward(스펙→분해)만으로는 마일스톤 reorg 시 잔여 자산을 인식하지 못하므로 backward 검증이 필수. 보강 시뮬레이션은 Phase 3.5 T1 질문 4.

**산출물**: 영향 분석 보고서 (내부, 사용자에게 제시하지 않음)

## Phase 2: 위계 판정 & 논의

작업 규모에 따라 에픽/그룹/단일 구조 선택 → 스펙 방향 논의.

### 위계 정의

| 위계 | 단위 | GitHub 대응 |
|------|------|------------|
| **에픽** | 새 제품 가치 + 복수 관심사 | **마일스톤** (Milestone) |
| **그룹** | 단일 관심사, 2-5 태스크 | 부모 이슈 (Sub-issues로 자식 묶음) |
| **단일** | 단일 패키지·단일 PR | 이슈 1개 (`/process-ticket` 1회 실행) |

정성 기준이 정량 기준보다 우선한다.

### 태스크 크기 가이드라인 (context rot 방지)

| 기준 | 상한 |
|------|------|
| 예상 변경 파일 수 | 5개 이하 |
| 예상 코드 변경량 | 신규 300줄 / 수정 200줄 이하 |
| 관여 패키지 수 | 1개 (cross-cutting 제외) |
| 수용 기준 항목 수 | 3-5개 |

### 병렬성 극대화 전략

- 인터페이스(ABC 기반 인터페이스) 정의 태스크를 항상 **선행**으로 배치 — 구현체 태스크들이 병렬 진행 가능
- 패키지 간 독립 작업은 동일 선행 조건 하에 병렬 배치
- 여러 패키지에 같은 패턴을 반복 적용하는 경우, 첫 번째를 **레퍼런스 구현**으로 지정하고 나머지에 "참조" 관계를 명시

## Phase 2.5: SDD 스펙 artifact 캡처

11섹션(비즈니스 의도·가정·US (User Story)/Given-When-Then·FR (Functional Requirement)·도메인 계약·도메인 규칙·경계·상호작용·범위 밖·SC (Success Criteria)·self-review) 구조화. `[NEEDS CLARIFICATION]` 마커 0개 + Constitution Check 통과 후 사용자 승인 (자명한 티켓은 생략).

**상세**: `phases/phase-2_5-spec.md`

## Phase 3: 분해 artifact & 의존성 그래프 & FR/SC 커버리지

태스크 분해 + 메타데이터(참조 US (User Story), 담당 FR (Functional Requirement), 기여 SC (Success Criteria)) + 쓰기 충돌 매트릭스 + 레이어 기반 선후 + 부모 의존 상속 + **FR/SC 커버리지 매핑** + DAG (Directed Acyclic Graph) 검증 + 본문 draft 생성 → 승인.

### 검증 항목

1. 순환 의존 없음 확인 (DAG 검증)
2. 크리티컬 패스 식별
3. 병렬 실행 가능한 태스크 그룹 식별
4. FR 커버리지 누락 0건 (모든 FR이 1개 이상 태스크에 매핑)
5. SC 커버리지 누락 0건 (모든 SC가 1개 이상 태스크 산출물 합으로 도달 가능)

### 사용자 승인

분해 결과를 사용자에게 제시하고 `AskUserQuestion`으로 승인을 받는다. 승인 없이 Phase 3.5로 진행하지 않는다.

## Phase 3.5: 스펙 시뮬레이션 게이트 (Soft Block)

서브에이전트로 cold reading 시뮬레이션. T1(티켓별 모호함·silent assumption), T2(에픽·그룹 DAG (Directed Acyclic Graph) 모순), T3(에픽 SC (Success Criteria) value drift) 3-tier. 결과는 검토 후보 리스트로 통합 → `AskUserQuestion` Soft block (전부 기각 시 항목별 사유 1줄 강제).

**상세**: `phases/phase-3_5-simulate.md`

## Phase 4: 기계적 이슈 생성

Phase 3-8 draft를 그대로 전송하여 GitHub 이슈 생성. **11항목 self-check** (마커 0 / US (User Story) 본문 인용 / FR (Functional Requirement)-SC (Success Criteria) 역참조 / Constitution 등) + Phase 3.5 게이트 통과 확인 + 필수 라벨 + top-down 생성 순서.

### 이슈 본문 작성 규칙 (UTF-8 깨짐 방지)

**`--body` 인라인 대신 `--body-file` 사용 필수:**

```bash
# 1. Write 도구로 임시 파일에 본문 작성
# /tmp/issue_{번호}.md 에 마크다운 본문을 Write 도구로 작성

# 2. --body-file로 이슈 생성
gh issue create --title "{제목}" --body-file /tmp/issue_{번호}.md \
  --label "{라벨}" --milestone "{마일스톤}" --project "Spakky Roadmap"
```

셸의 heredoc/문자열 처리 과정에서 multi-byte UTF-8 문자(한국어 등)가 바이트 경계에서 잘려 mojibake가 발생한다. `--body-file`은 파일을 직접 읽으므로 셸 문자열 처리를 우회하여 깨짐을 방지한다.

### 생성 순서 (top-down)

이슈 번호를 상위에서 참조해야 하므로, top-down 순서로 생성한다:

1. **에픽 마일스톤** 생성 (`gh api repos/{owner}/{repo}/milestones`)
2. **부모 이슈** 생성 (그룹 구조에서만) — 마일스톤 연결 + 프로젝트 연결
3. **자식 태스크 이슈** 생성 — 부모 번호 본문 참조 + 마일스톤/프로젝트 연결
4. **선후 관계** 설정 (`addBlockedBy` GraphQL mutation)
5. **Sub-issues 위계** 설정 (`addSubIssue` GraphQL mutation, 그룹 구조)

### GitHub Sub-issues / blockedBy GraphQL

```bash
# 이슈 node ID 조회
gh api graphql -f query='{ repository(owner: "{owner}", name: "{repo}") { issue(number: {N}) { id } } }' --jq '.data.repository.issue.id'

# Sub-issue 위계 설정
gh api graphql -f query='mutation { addSubIssue(input: { issueId: "{PARENT_ID}", subIssueId: "{CHILD_ID}" }) { issue { number } subIssue { number } } }'

# blockedBy 관계 설정
gh api graphql -f query='mutation { addBlockedBy(input: { issueId: "{ISSUE_ID}", blockingIssueId: "{BLOCKING_ISSUE_ID}" }) { issue { number } } }'
```

**주의**: `gh issue edit --add-sub-issue`는 지원되지 않으므로 반드시 GraphQL mutation을 사용한다.

## Phase 5: 결과 보고

생성된 이슈 목록 + 의존성 Mermaid + 크리티컬 패스 + 병렬 그룹 보고.

```
## 이슈 생성 완료

마일스톤: {마일스톤 제목}

### 태스크
| 태스크 | 자식 | 선행 의존 |
|--------|------|-----------|
| #{T1} {제목} | -- | -- |
| #{T2} {제목} | #{S1}, #{S2} | #{T1} |

### 의존성 그래프
{Mermaid 다이어그램}

### 크리티컬 패스
#{T1} -> #{T2} -> ...

### 병렬 실행 가능 그룹
- 그룹 A: #{T1}, #{T3} (선행 없음)
- 그룹 B: #{T2}, #{T4} (선행: #{T1})
```

---

## 이슈 템플릿 & Stale 방지 원칙

마일스톤 / 부모 이슈 / 태스크 템플릿과 Stale 방지 원칙은 `templates.md` 참조.

---

## 규칙

- **SDD (Spec-Driven Development) 원칙**: Phase 2.5 스펙 artifact (US (User Story)/FR (Functional Requirement)/SC (Success Criteria) + Given-When-Then) 와 Phase 3 분해 artifact (FR/SC 커버리지 + DAG (Directed Acyclic Graph)) 를 먼저 확정하고, Phase 4는 기계적 주입이다. Phase 4에서 본문을 재작성·보강하지 않는다.
- **`[NEEDS CLARIFICATION]` 마커 게이트**: Phase 2.5 §11 self-review에서 마커 0개 확인, Phase 4 self-check에서 본문 grep으로 재확인. 1개라도 발견되면 Phase 3 진입 차단.
- **FR/SC traceability 필수**: 모든 태스크는 담당 FR 1개 이상을 가지며, 모든 FR은 정확히 1개 이상의 태스크에 매핑. Phase 3 커버리지 표 누락 0이 Phase 4 진입 조건.
- **Phase 3.5 시뮬레이션 게이트**: 자명 티켓 외 모든 규모는 서브에이전트 cold reading으로 사전 검출 (T1 모호함, T2 DAG 모순, T3 SC drift). Soft block — 검토 후보 리스트를 사용자가 일괄 의사결정. "전부 기각"은 항목별 사유 1줄 강제로 묵시적 무시 방지. 비용 추정 결과 상단 표시.
- **자명한 티켓 승인 생략 조건** (Phase 2.5, Phase 3, Phase 3.5 모두 별도):
  - 단일 구조 + 단일 패키지 + 직접 도출 가능 + **마커 0개**이면 Phase 2.5 스펙 승인 생략.
  - 위 조건 + 쓰기 충돌 없음이면 Phase 3 분해 승인도 생략.
  - 자명 생략 시에도 §1·§3 US 1개·§4 FR 1-3개·§10 SC 1-2개는 작성 (Phase 4 self-check 차단점이므로 누락 시 자동 복귀).
- **마일스톤 판정 기준**을 준수한다: 에픽(새 제품 가치 + 복수 관심사) → 마일스톤, 그룹(단일 관심사, 2-5 태스크) → 부모 이슈, 단일 → 이슈 1개. 정성 기준이 정량 기준보다 우선한다.
- **기존 마일스톤 재사용 우선**: 새 마일스톤을 만들기 전에 Phase 1에서 조회한 기존 마일스톤과 범위가 겹치는지 확인한다.
- **의존성 규칙**:
  - 쓰기 충돌 매트릭스로 병렬 가능성을 검증한다.
  - 레이어 기반 선후(Port 정의 → 구현 → 배선)를 자동 적용한다.
  - 부모 간 의존은 자식으로 상속되며, 대표 태스크(인터페이스 확정)를 의존 대상으로 삼는다.
  - 자식 태스크의 `blockedBy`는 동일 부모 형제 또는 다른 부모의 대표 태스크만 허용.
- **이슈 본문의 Stale 방지**: 파일 경로/시그니처/커밋은 금지, 도메인 스펙은 최대 밀도.
- **코드베이스 분석은 Explore 서브에이전트**로 실행한다.
- **이슈 생성은 top-down 순서**: 마일스톤 → 부모 이슈 → 자식 태스크 → 선행 관계.
- 모든 이슈에 `--project "Spakky Roadmap"` 과 (마일스톤이 있으면) `--milestone "{마일스톤}"` 을 연결한다.
- **이슈 본문은 Write 도구로 임시 파일에 작성** 후 `--body-file`로 전달한다 (UTF-8 깨짐 방지).
- 그룹의 자식 이슈는 GraphQL `addSubIssue` mutation으로 부모와 위계를 연결한다.
- 선행 의존은 GraphQL `addBlockedBy` mutation으로 설정한다.
- 각 Phase 전환 시 사용자에게 현재 단계를 간결하게 알린다.

$ARGUMENTS
