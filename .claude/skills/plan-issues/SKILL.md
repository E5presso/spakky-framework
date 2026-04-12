---
name: plan-issues
description: 자연어 기능 방향성을 받아 마일스톤/태스크/서브태스크 3단 위계의 GitHub 이슈를 자동 생성합니다.
argument-hint: "<기능 방향성 설명>"
user-invocable: true
---

# Plan Issues — 기능 기획 → GitHub 이슈 자동 생성

자연어로 설명된 기능 방향성을 받아, 에이전트(`/process-ticket`)가 소비할 수 있는 구체적인 GitHub 이슈 티켓을 3단 위계로 자동 생성한다.

## 사용법

```
/plan-issues 프레임워크에 헬스체크 엔드포인트를 추가하고 싶어
```

인자: 기능 방향성 설명 (자연어)

---

## Phase 0: 입력 수집

1. `$ARGUMENTS`에서 기능 방향성을 수집한다.
2. 입력이 모호하거나 불충분하면 `AskUserQuestion`으로 보강한다:
   ```yaml
   question: "기능 방향성을 더 구체화하겠습니다. 아래 항목을 확인해주세요."
   header: "입력 보강"
   options:
     - label: "목표 확인"
       description: "이 기능이 해결하는 핵심 문제는 무엇입니까?"
     - label: "범위 확인"
       description: "영향받는 패키지/계층을 알고 있다면 알려주세요"
     - label: "제약 확인"
       description: "호환성, 성능, 외부 의존성 등 제약 조건이 있습니까?"
   ```
3. 입력이 충분히 명확하면 `AskUserQuestion` 없이 Phase 1로 진행한다.

## Phase 1: 코드베이스 분석

**Explore 서브에이전트**로 현재 코드베이스를 분석한다.

1. `ARCHITECTURE.md`, `CONTRIBUTING.md` 읽기
2. 의존성 그래프에서 영향받는 패키지 식별
3. 기존 유사 패턴 탐색 (참조할 수 있는 기존 구현 파악)
4. `docs/adr/` 디렉토리에서 관련 ADR 존재 여부 확인
5. 영향 패키지별 현재 공개 인터페이스(ABC, Protocol) 파악

**산출물**: 영향 분석 보고서 (내부, 사용자에게 제시하지 않음)

## Phase 2: 작업 분해

기능을 **에픽(마일스톤) → 태스크 → 서브태스크** 3단 위계로 분해한다.

### 위계 정의

| 위계 | 단위 | GitHub 대응 |
|------|------|------------|
| **에픽** | 기능 전체 | **마일스톤** (Milestone) |
| **태스크** | 패키지 또는 관심사 | 이슈 (하나의 PR, `/process-ticket` 1회 실행) |
| **서브태스크** | 태스크 분할 단위 | 이슈 (태스크가 너무 클 때만 생성) |

### 분해 규칙

1. **에픽**: 기능 전체를 하나의 마일스톤으로 묶는다. 기능이 매우 크면 복수 마일스톤 가능.
2. **태스크**: 하나의 패키지 또는 하나의 관심사(cross-cutting concern)에 대응한다. **기본 작업 단위이며, `/process-ticket`의 소비 단위.**
3. **서브태스크**: 태스크가 크기 가이드라인을 **초과할 때만** 분할하여 생성한다. 기본적으로 태스크 = 서브태스크 없이 단독 이슈.

### 태스크 크기 가이드라인 (context rot 방지)

| 기준 | 상한 |
|------|------|
| 예상 변경 파일 수 | 5개 이하 |
| 예상 코드 변경량 | 신규 300줄 / 수정 200줄 이하 |
| 관여 패키지 수 | 1개 (cross-cutting 제외) |
| 수용 기준 항목 수 | 3-5개 |

- 가이드라인 이내이면 **서브태스크 없이 태스크 이슈 하나로 처리**.
- 가이드라인을 초과하면 서브태스크로 분할한다.
- 분할 시 "구현 + 테스트"는 반드시 **같은 서브태스크**에 포함한다 (맥락 유지).

### 맥락 전파 원칙

각 태스크/서브태스크 이슈는 **그 이슈만 읽고도 "왜 이 작업이 필요한지"를 이해할 수 있어야 한다.** `/process-ticket` 에이전트는 에픽 수준의 기획 논의를 보지 못하므로, 상위 맥락을 각 이슈에 내려보내야 한다.

- **에픽 → 태스크**: 에픽의 목적·배경을 태스크 본문의 "배경 및 동기" 섹션에 요약하여 전파
- **태스크 → 서브태스크**: 태스크의 목적을 서브태스크 본문의 "배경 및 동기" 섹션에 요약하여 전파
- **설계 의도**: "왜 이 방식인지" (대안 대비 선택 이유)를 "배경 및 동기"에 포함 — 에이전트가 임의로 다른 방식을 선택하는 것을 방지

### 병렬성 극대화 전략

- 인터페이스(ABC/Protocol) 정의 태스크를 항상 **선행**으로 배치 — 구현체 태스크들이 병렬 진행 가능
- 패키지 간 독립 작업은 동일 선행 조건 하에 병렬 배치
- 여러 패키지에 같은 패턴을 반복 적용하는 경우, 첫 번째를 **레퍼런스 구현**으로 지정하고 나머지에 "참조" 관계를 명시

## Phase 3: 의존성 그래프 & 검증

### 검증 항목

1. 순환 의존 없음 확인 (DAG 검증)
2. 크리티컬 패스 식별
3. 병렬 실행 가능한 태스크 그룹 식별
4. 서브태스크 크기가 가이드라인 범위 내인지 확인
5. 각 서브태스크가 독립 검증 가능한지 확인 (테스트 포함)

### 사용자 승인

분해 결과를 사용자에게 제시하고 `AskUserQuestion`으로 승인을 받는다:

```yaml
question: "아래 작업 분해 결과를 검토해주세요."
header: "작업 분해 승인"
options:
  - label: "승인"
    description: "이 분해 구조로 이슈를 생성합니다"
  - label: "수정 요청"
    description: "특정 태스크/서브태스크를 변경합니다 (notes에 기재)"
  - label: "재분해"
    description: "Phase 2부터 다시 시작합니다"
```

- "수정 요청" 선택 시 사용자의 notes를 반영하여 분해를 갱신한 뒤 다시 승인을 요청한다.
- "재분해" 선택 시 Phase 2를 처음부터 재실행한다.
- **승인 없이 Phase 4로 진행하지 않는다.**

## Phase 4: 이슈 생성

승인된 분해 구조를 GitHub 이슈로 생성한다.

### 이슈 본문 작성 규칙 (UTF-8 깨짐 방지)

**`--body` 인라인 대신 `--body-file` 사용 필수:**

```bash
# 1. Write 도구로 임시 파일에 본문 작성
# /tmp/issue_{번호}.md 에 마크다운 본문을 Write 도구로 작성

# 2. --body-file로 이슈 생성
gh issue create --title "{제목}" --body-file /tmp/issue_{번호}.md --label "{라벨}" --project "Spakky Roadmap"
```

셸의 heredoc/문자열 처리 과정에서 multi-byte UTF-8 문자(한국어 등)가 바이트 경계에서 잘려 mojibake가 발생한다.
`--body-file`은 파일을 직접 읽으므로 셸 문자열 처리를 우회하여 깨짐을 방지한다.

### 생성 순서 (bottom-up)

이슈 번호를 상위에서 참조해야 하므로, bottom-up 순서로 생성한다:

1. **에픽 마일스톤** 생성 (`gh api repos/{owner}/{repo}/milestones`)
2. **서브태스크 이슈** 생성 — 마일스톤 연결 + 프로젝트 연결
3. **태스크 이슈** 생성 — 서브태스크 번호를 본문에 참조 + 마일스톤/프로젝트 연결

### 마일스톤 생성 (에픽)

```bash
gh api repos/{owner}/{repo}/milestones -f title="{에픽 제목}" -f description="{설명}"
```

### 이슈 생성 명령

```bash
gh issue create --title "{제목}" --body-file /tmp/issue_{id}.md \
  --label "{라벨}" --milestone "{마일스톤 제목}" --project "Spakky Roadmap"
```

### GitHub Sub-issues 위계 설정

이슈 생성 후, GraphQL API로 부모-자식 관계를 설정한다:

```bash
# 1. 이슈의 node ID 조회
gh api graphql -f query='{ repository(owner: "{owner}", name: "{repo}") { issue(number: {N}) { id } } }' --jq '.data.repository.issue.id'

# 2. addSubIssue mutation으로 위계 설정
gh api graphql -f query='mutation { addSubIssue(input: { issueId: "{PARENT_ID}", subIssueId: "{CHILD_ID}" }) { issue { number } subIssue { number } } }'
```

**주의**: `gh issue edit --add-sub-issue`는 지원되지 않으므로 반드시 GraphQL mutation을 사용한다.

### 라벨

- 태스크/서브태스크: 이슈 성격에 맞는 라벨 (`enhancement`, `bug` 등)

## Phase 5: 결과 보고

생성된 이슈 목록과 의존성 다이어그램을 사용자에게 보고한다:

```
## 이슈 생성 완료

마일스톤: {마일스톤 제목}

### 태스크

| 태스크 | 서브태스크 | 선행 의존 |
|--------|-----------|-----------|
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

## 이슈 템플릿

> 상세 템플릿(태스크·서브태스크·마일스톤·stale 방지·선후행 관계)은 `plan-issues/templates.md` 참조.

---

## 규칙

- Phase 3에서 사용자 승인 없이 이슈를 생성하지 않는다.
- 태스크가 크기 가이드라인 이내이면 서브태스크를 생성하지 않는다.
- 이슈 본문에 파일 경로를 하드코딩하지 않는다 (Stale 방지 원칙 준수).
- 코드베이스 분석은 **Explore 서브에이전트**로 실행한다.
- 이슈 생성은 **bottom-up** (마일스톤 → 서브태스크(있으면) → 태스크) 순서로 진행한다.
- 이슈 본문은 **Write 도구로 임시 파일에 작성** 후 `--body-file`로 전달한다 (UTF-8 깨짐 방지).
- 모든 이슈에 `--project "Spakky Roadmap"` 과 `--milestone "{마일스톤}"` 을 연결한다.
- 서브태스크가 있는 경우 GraphQL `addSubIssue` mutation으로 위계를 설정한다.
- 각 Phase 전환 시 사용자에게 현재 단계를 간결하게 알린다.

$ARGUMENTS
