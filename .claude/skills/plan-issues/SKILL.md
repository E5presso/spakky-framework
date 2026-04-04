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

### 마일스톤 (에픽)

마일스톤의 description 필드에 아래 내용을 기술한다:

```
{기능의 목적과 배경을 2-3문장으로 서술}

완료 기준:
- {검증 가능한 기준 1}
- {검증 가능한 기준 2}
```

### 태스크 (기본 작업 단위)

**제목 형식**: `[{에픽약어}] {태스크명}`
- 예: `[Tracing] spakky-tracing 코어 패키지 생성`
- 순번을 붙이지 않는다. 개발 순서는 이슈 본문의 "선행 이슈" 필드로 결정된다.

> `/process-ticket`이 소비하는 기본 단위. **목표, 수용 기준, 제약 사항**을 명확히 기술한다.

```markdown
# {태스크명}

## 목표

{이 태스크가 달성해야 할 것을 1-2문장으로. 명확하고 검증 가능하게.}

## 선행 이슈

- [ ] #{선행번호}

> 선행 이슈가 없으면 이 섹션을 생략한다.
> 태스크 리스트(`- [ ] #N`) 형식으로 작성하면 GitHub이 자동으로 "Tracked by" 관계를 인식하여 Relationships UI에 표시된다.

## 작업 범위

{수정/생성할 대상의 역할과 책임을 서술}

- 대상 패키지: `{패키지명}`
- 참조할 기존 패턴: `{유사 구현이 있는 패키지/모듈}의 {패턴명} 패턴 참조`

## 수용 기준

- [ ] {검증 가능한 기준 1}
- [ ] {검증 가능한 기준 2}
- [ ] 관련 테스트 작성 및 통과
- [ ] lint + type check 통과

## 제약 사항

- {제약 1}
- {제약 2}

## 참고 컨텍스트

{에이전트가 작업 시작 시 읽어야 할 문서/코드 위치를 안내. 경로가 아닌 탐색 지시로 작성.}

- ARCHITECTURE.md 의존성 그래프 섹션
- `{패키지명}` 패키지의 기존 인터페이스 (ABC/Protocol)
- {관련 ADR 문서 제목}
```

### 서브태스크 (태스크 분할 시에만)

**제목 형식**: `[{에픽약어}] {서브태스크명}`
- 예: `[Tracing] TraceContext dataclass 및 contextvars 바인딩 구현`

> 태스크가 크기 가이드라인을 초과할 때만 생성. 태스크 템플릿과 동일한 형식을 사용하되, 본문에 **부모 태스크 참조**를 추가한다.

```markdown
# {서브태스크명}

## 목표

{이 서브태스크가 달성해야 할 것을 1-2문장으로.}

## 선행 이슈

- [ ] #{태스크번호}
- [ ] #{선행번호}

## 작업 범위

{태스크 템플릿과 동일}

## 수용 기준

{태스크 템플릿과 동일}

## 제약 사항

{태스크 템플릿과 동일}

## 참고 컨텍스트

{태스크 템플릿과 동일}
```

---

## Stale 방지 원칙

이슈 본문 작성 시 아래 원칙을 반드시 준수한다:

1. **파일 경로 하드코딩 금지**: "`spakky-tracing` 패키지의 context 모듈"처럼 패키지/모듈 수준으로 지칭
2. **코드 스니펫은 인터페이스(시그니처)만**: 구현체 전문을 이슈에 넣지 않음
3. **"참조할 기존 패턴" 안내**: 파일 경로 대신 패턴 레벨로 지시 (예: "spakky-rabbitmq의 Transport 구현 패턴 참조")
4. **탐색 지시어 사용**: "ARCHITECTURE.md의 의존성 그래프 섹션 참조", "`{패키지}` 패키지의 기존 ABC 클래스 확인"
5. **버전/커밋 고정 금지**: 특정 커밋 해시나 버전을 이슈에 기록하지 않음
6. **ADR 참조는 문서 제목으로**: 경로 대신 "ADR-0004: 분산 트레이싱 아키텍처" 형태로 참조

---

## 선후행 관계 표현

다음 메커니즘을 조합한다:

1. **Blocked by (Relationships UI)**: GraphQL `addBlockedBy` mutation으로 선행 이슈 관계를 설정한다. GitHub Relationships UI에 "Blocked by / Blocking" 관계가 표시된다.
   ```bash
   # 이슈 node ID 조회
   gh api graphql -f query='{ repository(owner: "{owner}", name: "{repo}") { issue(number: {N}) { id } } }' --jq '.data.repository.issue.id'

   # blocked by 관계 설정: {ISSUE}가 {BLOCKING_ISSUE}에 의해 블록됨
   gh api graphql -f query='mutation { addBlockedBy(input: { issueId: "{ISSUE_ID}", blockingIssueId: "{BLOCKING_ISSUE_ID}" }) { issue { number } } }'
   ```
2. **이슈 본문 메타데이터**: 이슈 본문에도 `## 선행 이슈` 섹션에 태스크 리스트(`- [ ] #N`)로 선행 이슈를 기재한다 (가독성 + `/process-ticket` 파싱용).
3. **마일스톤**: 태스크 이슈를 에픽 마일스톤에 연결하여 진행률 추적
4. **GitHub Sub-issues**: GraphQL `addSubIssue` mutation으로 부모-자식 위계 설정 (서브태스크가 있는 경우에만)
5. **크리티컬 패스 & 병렬 그룹**: Phase 5 결과 보고에 명시

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
