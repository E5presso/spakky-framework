---
name: audit-codebase
description: 다관점 전문가 서브에이전트를 병렬 파견하여 코드베이스의 개선점을 발굴하고 심각도별로 통합 보고합니다.
argument-hint: "[--all | <package-name> | <path>]"
user-invocable: true
---

# Audit Codebase — 다관점 병렬 개선점 발굴

코드베이스를 **여러 전문가 관점(아키텍처 / 타입안전 / 테스트 / 성능 / 보안 / 의존성 / 기술부채)** 으로 병렬 감사하여 개선점을 발굴·병합·분류한다. gstack의 "Review Army" 패턴에서 영감을 얻었다.

## 기존 스킬과의 역할 구분

| 스킬 | 입력 | 목적 | 비고 |
|------|------|------|------|
| `/review-code` | `git diff` | **변경된** 코드의 위반 감지 | diff 범위 |
| `/refactor-code` | 하네스 규칙 | 규칙 위반 전수 감사 **+ 자동 수정** | 규칙 정적 감사 |
| **`/audit-codebase`** | **기존 코드 전체** | **개선 여지 발굴** (버그·부채·설계) | **다관점 휴리스틱** |
| `/investigate` | 증상/이슈 | 특정 버그 근본 원인 추적 | 증상 기반 |

`audit-codebase`는 "알려진 위반"이 아니라 **"지금까지 보이지 않던 개선점"** 을 찾는다. 결과는 새 Issue 후보가 된다.

## 사용법

```
/audit-codebase                          # 전체 모노레포 감사 (기본)
/audit-codebase --changed                # git diff 기반 변경 패키지만
/audit-codebase spakky-event             # 특정 패키지만
/audit-codebase core/spakky-saga/src     # 특정 경로만
```

---

## Phase 1: 감사 범위 확정

### 1-1. 입력 해석

- **인자 없음** → 전체 모노레포 (`core/*` + `plugins/*`)
- `--changed` → `git diff --name-only origin/main...HEAD`에서 패키지 자동 추출
- **패키지명** → 해당 패키지
- **경로** → 해당 디렉토리

### 1-2. 컨텍스트 로드

아래를 읽어 감사 기준을 수립한다:

- `CLAUDE.md`, `ARCHITECTURE.md`, `CONTRIBUTING.md`
- `.claude/rules/*.md`
- 대상 패키지의 `README.md`, `pyproject.toml`
- 최근 ADR 목록 (`docs/adr/`)

### 1-3. 적응형 게이팅

대상 규모에 따라 파견할 전문가 수를 조절한다:

| 대상 규모 | 기본 파견 전문가 |
|----------|-----------------|
| 단일 파일/모듈 | Architecture, TypeSafety, Tests |
| 단일 패키지 | + Performance, TechDebt |
| 다중 패키지 / 전체 | 전 전문가 (7종) |

---

## Phase 2: 병렬 전문가 파견 (Review Army)

**Explore 서브에이전트**를 관점별로 병렬 실행한다. 각 서브에이전트는 **fresh context**에서 편향 없이 조사한다.

### 2-1. 전문가 카탈로그

각 전문가는 고유한 휴리스틱과 질문 프레임을 가진다.

#### Architect — 아키텍처 설계

- 레이어 역방향 의존, 플러그인 간 직접 참조
- Entity/ValueObject/AggregateRoot 경계 붕괴
- AOP Aspect 동기/비동기 쌍 누락
- 공개 API 네이밍 일관성 (`I`, `Abstract`, `Error`, `Async`)
- DI 컨테이너 등록 누락, 순환 의존

**참조 규칙**: `.claude/rules/domain.md`, `.claude/rules/aspect.md`, `.claude/rules/monorepo.md`

#### TypeSafety — 타입 안전

- `Any` 사유 없는 사용, opt-out 주석 사유 누락
- `@override` 누락 (부모 메서드 재정의)
- 과도한 `cast()` / `# type: ignore`
- `getattr`/`hasattr`/`setattr` 동적 접근
- Protocol/ABC 시그니처 불일치
- `uv run pyrefly check` 실행 결과도 수집

**참조 규칙**: `.claude/rules/python-code.md`

#### Tests — 테스트 품질

- 커버리지 구멍 (변경 대비 누락, 엣지 케이스 부재)
- `class TestXxx`, docstring 누락, 네이밍 패턴 위반
- Flaky 요소 (`time.sleep`, `datetime.now()`, 순서 의존, 네트워크)
- 과도한 mock → 실제 행동 미검증
- 속성 기반 테스트 적용 여지 (불변식 검증 대상)

**참조 규칙**: `.claude/rules/test-writing.md`

#### Performance — 성능

- 루프 내 I/O, N+1 쿼리 패턴
- `async` 함수에서 동기 블로킹 호출
- 불필요한 리스트/딕셔너리 재생성 (제너레이터 적용 가능)
- 캐시 가능한 순수 함수 누락

#### Security — 보안

- 역직렬화 함정 (`pickle`, `yaml.load`)
- 로그에 민감정보 노출
- SQL/Shell injection 가능성
- JWT/암호 처리 위임 경계 확인 (`plugins/spakky-security`)
- 외부 입력 검증 누락 (boundary validation)

#### Dependencies — 의존성 건강도

- 미사용 dependency, `pyproject.toml` vs 실제 import 괴리
- 동일 기능에 대한 중복 라이브러리
- 레이어/모노레포 의존 방향 위반
- outdated 메이저 버전 뒤처짐

**참조 규칙**: `.claude/rules/dependencies.md`

#### TechDebt — 기술 부채

- `TODO`/`FIXME`/`XXX`/`HACK` 주석 집계
- 200줄 초과 메서드, 50줄 초과 함수
- 사실상 죽은 코드 (호출되지 않는 public 심볼)
- 사유 없는 `# pragma: no cover`, `# type: ignore`
- 중복 로직 (3회 이상 반복되는 패턴)
- 오래된 deprecated 코드 잔재

### 2-2. 서브에이전트 프롬프트 템플릿

각 서브에이전트에게 **동일 구조의 완전한 컨텍스트**를 전달한다:

```
[역할]
당신은 {전문가명} 전문가다. {관점 설명}.

[감사 대상]
- 범위: {Phase 1에서 확정된 경로 목록}
- 코드베이스 컨텍스트: {CLAUDE.md 요약, 관련 규칙 파일 경로}

[휴리스틱]
{해당 전문가의 체크리스트 전체}

[금지 — False Positive 방지]
- 기존 미변경 코드의 "스타일 개선" 제안 금지
- 요청되지 않은 추상화/유연성 제안 금지 (behavioral-guidelines §2)
- 이미 ADR/주석으로 정당화된 패턴을 문제로 보고하지 말 것
- 규칙 파일에 명시된 예외(sys.version_info 가드 등)는 유효로 처리

[출력 형식]
## {전문가명} 감사 결과

### Findings
- [심각도] [파일:라인] {제목}
  - 증거: {코드 스니펫 또는 인용}
  - 영향: {왜 문제인가}
  - 제안: {구체적 수정 방향 — 파일/함수 수준}

### Clean (감사했으나 위반 없음)
- {검토한 체크리스트 항목}

심각도: Critical(런타임 위험) / High(하네스·설계 위반) / Medium(품질 저하) / Low(가독성·부채)
```

### 2-3. 병렬 실행 규칙

- **서로 다른 파일을 조사**하는 전문가들은 동시 파견 (충돌 없음)
- 한 번에 최대 **4개 서브에이전트** 동시 실행 → 나머지는 순차
- 전문가 간 **동일 파일 수정 금지** (이 스킬은 읽기 전용)
- 각 서브에이전트는 `isolation: "worktree"` **사용하지 않음** — 읽기 전용이므로 불필요

---

## Phase 3: 수집 및 병합

### 3-1. 중복 제거

동일 `[파일:라인]`에 여러 전문가가 보고한 항목은 병합:
- 더 높은 심각도를 채택
- 제안은 **상호 보완**되면 통합, **충돌**하면 양쪽 모두 보고 (사용자 판단)

### 3-2. 교차 증거 강화

**2명 이상의 전문가가 독립적으로 같은 항목을 지적**하면 심각도를 1단계 상향한다. (모델 간 합의 = 신뢰도)

### 3-3. 범위 외 발견 ("See Something, Say Something")

감사 대상 **밖에서 발견한 명백한 문제**는 별도 섹션에 기록한다. 무시하지 않되, 해결은 별도 이슈로 분리.

---

## Phase 4: 통합 보고

아래 형식을 **텍스트로 화면에 출력**한다.

```markdown
## 코드베이스 감사 결과

**범위**: {대상 경로 목록}
**파견 전문가**: {전문가 수}명
**총 발견**: Critical N / High N / Medium N / Low N

---

### Critical — 즉시 조치

| # | 위치 | 제목 | 발견 전문가 | 제안 |
|---|------|------|------------|------|
| 1 | [파일:라인] | {제목} | Architect, TypeSafety | {한 줄 제안} |

### High — 우선 처리

(동일 표 형식)

### Medium — 품질 개선

(동일 표 형식)

### Low — 부채 정리

(동일 표 형식, 요약 카운트만 가능)

---

### 전문가별 요약

- **Architect**: {핵심 발견 2-3줄}
- **TypeSafety**: ...
- **Tests**: ...
- **Performance**: ...
- **Security**: ...
- **Dependencies**: ...
- **TechDebt**: ...

### 범위 외 발견

{있으면 기록, 없으면 "없음"}

### 교차 증거 (2명 이상 지적)

- [파일:라인] {제목} — 지적 전문가: {목록}
```

---

## Phase 5: 다음 액션

`AskUserQuestion`으로 후속 행동을 선택받는다.

```yaml
question: "감사 결과를 어떻게 처리할까요?"
header: "Audit 완료"
options:
  - label: "Critical/High를 Issue로 생성"
    description: "선택한 심각도를 GitHub Issue로 자동 생성 (notes에 범위 지정 가능)"
  - label: "전체 보고서를 Issue로 생성"
    description: "감사 보고서 전체를 하나의 트래킹 Issue로 생성"
  - label: "/refactor-code로 연계"
    description: "하네스 규칙 위반 항목을 /refactor-code로 자동 수정"
  - label: "종료"
    description: "보고서만 확인하고 종료"
```

### 5-1. Issue 생성 시 규칙

- 제목: `[audit] {심각도} — {간결한 제목}`
- 본문: 발견 전문가 / 증거 스니펫 / 영향 / 제안 / 참조 규칙 파일 경로
- 라벨: `audit`, `{심각도}` (존재할 때만)
- **한 Issue = 한 개선점**. 묶지 않는다 (추적성).

---

## 규칙

- **쓰기 금지**: 이 스킬은 **읽기 전용**이다. 코드/문서를 수정하지 않는다. 수정은 후속 스킬(`/refactor-code`, `/process-ticket`)이 담당.
- **증거 기반**: 모든 발견은 `[파일:라인]`과 코드 증거를 동반한다. "아마도" 금지.
- **Fresh Context 원칙**: 전문가 서브에이전트는 항상 **Explore**로 실행하여 self-confirmation bias를 방지한다.
- **False Positive 억제**: 기존 미변경 코드의 스타일, 요청되지 않은 추상화, 이미 정당화된 패턴은 보고하지 않는다.
- **범위 고정**: Phase 1에서 확정한 범위 밖은 "범위 외 발견"으로만 기록. 본 보고서 표에 섞지 않는다.
- **루트 도구 실행 금지**: 검증을 위해 `pyrefly`를 돌릴 때는 반드시 패키지 디렉토리 내에서 `uv run pyrefly check`.

$ARGUMENTS
