---
name: evaluate-harness
description: 하네스가 선언한 규칙이 실제로 차단되는지 외부 서브에이전트로 독립 검증합니다. 선언-실행 단절, 회피 경로, 포인터 무효점을 적발하고 보고만 수행하며 직접 보강하지 않습니다.
argument-hint: "[scope: rules|skills|all]"
user-invocable: true
---

# Evaluate Harness — 하네스 외부 검증

하네스 규칙이 **선언만 있고 실제 차단되지 않는** 단절을 외부 서브에이전트로 검증한다. 자기확증 편향을 구조적으로 차단하기 위해 **사전적 회귀 검증** 용도다.

## 본분 (Boundary)

본 스킬의 본분은 **평가와 위임**이다. 보강(코드/설정/스킬 본문 수정)은 본분 밖이며, 사용자가 "전부 자동으로"라고 응답해도 본 스킬 안에서 직접 수정에 진입하지 않는다.

- ✅ 본분 안: 갭 식별 → 다축 분류 → 보고서 작성 → 위임 경로 제시 → 사용자 승인 시 위임 호출
- ❌ 본분 밖: `pyproject.toml`/`settings.json`/스킬 본문/규칙 본문 직접 편집, 코드베이스 위반 직접 수정, 신규 규칙 제안

본 경계는 charter §1 "scope creep 금지"와 §4-A "모호함을 스스로 채우지 않는다"의 직접 적용이다. 보강이 필요하면 별도 SSOT(`/optimize-harness`, `/plan-issues` → `/process-ticket`)로 위임한다.

## 사용법

```bash
/evaluate-harness            # 전체 평가
/evaluate-harness rules      # rules/*.md만
/evaluate-harness skills     # skills/*/SKILL.md만
```

자동 트리거:
- `/optimize-harness` Phase 7 (회귀 검증)
- 하네스 PR 머지 직후 (recommended, 수동)

---

## Phase 1: 평가 대상 수집

스코프에 따라 대상 파일을 수집한다:

- `rules`: `.claude/rules/*.md` 전체 + `CLAUDE.md`
- `skills`: `.claude/skills/*/SKILL.md` 전체 + 하위 phase·script
- `all`: 위 둘 + `.claude/settings.json`

각 파일의 **차단 선언**(금지 표현, 필수 표현, 게이트 표현)을 추출하여 평가 항목 목록을 만든다.

## Phase 2: 외부 서브에이전트 검증 (병렬)

`Explore` 또는 `general-purpose` 서브에이전트를 **카테고리별 병렬 spawn**한다. 각 서브에이전트에게:

- 평가 대상 규칙 1개 또는 1개 그룹
- 코드베이스 탐색 권한 (read-only)
- 다음 4축으로 검증하고 다축 분류로 보고하도록 지시

### 검증 4축

1. **선언-실행 단절**: 규칙이 차단을 선언하지만, 실제 코드/도구에서 차단되지 않는가?
   - 예: "src/에서 assert 금지" 선언인데 lint/hook이 차단하지 않음 → 단절.
2. **포인터 무효점**: 규칙이 다른 파일을 참조하는데, 그 파일이 없거나 해당 항목이 없는가?
3. **회피 경로**: 규칙을 형식만 지키고 의도를 우회하는 알려진 패턴이 코드베이스에 존재하는가?
4. **Stale 사실**: 규칙이 가정한 코드 구조·도구·버전이 현재와 다른가?

### 다축 분류 (필수)

각 발견은 다음 **3축**으로 동시 분류한다. 단일 severity 라벨로는 위임 경로가 갈리지 않으므로, 사용자와 에이전트 모두가 작업 종류를 즉시 식별할 수 있도록 강제한다.

| 축 | 값 | 정의 |
|----|----|------|
| **severity** | `critical` | 차단 선언이 실효되지 않음 → 규칙이 사실상 무효 |
|             | `warning`  | 부분적 enforcement 또는 일관성 결손 |
|             | `info`     | 문서·라벨링 수준의 개선 여지 |
| **regression-risk** | `none` | 변경이 코드 동작에 영향 없음 (포인터·문구·라벨) |
|                    | `low`  | lint/config 추가만, 기존 코드 변경 0건 예상 |
|                    | `medium` | 기존 코드 일부 수정 필요, 모듈 단위 회귀 검토 |
|                    | `high` | 프레임워크 코어/공유 인프라 변경, 전사 회귀 위험 |
| **scope** | `harness-only` | `.claude/` 내부에서 완결 (rules·skills·settings) |
|          | `config-only` | `pyproject.toml`/`pre-commit` 등 빌드 설정만 |
|          | `code-and-policy` | 코드 변경 + 정책 결정 동반 (ADR 후보) |
|          | `framework-core` | `core/spakky/`·AOP·DI 등 기반 동작 변경 |

**분류 규칙**:
- `severity:critical` 단독은 자동 진입을 의미하지 않는다. **위임 경로는 `(severity, regression-risk, scope)` 3축 조합**으로만 결정된다 (Phase 4 위임 매트릭스 참조).
- 같은 발견이 두 축의 다른 값을 동시에 갖는 것처럼 보이면 가장 보수적인(높은 위험·넓은 범위) 값을 선택한다.

## Phase 3: 보고서 통합

서브에이전트 결과를 메인이 통합한다. 각 항목은 다축 라벨을 명시한다:

```markdown
## Evaluate Harness 보고서

스코프: {scope}
평가 대상: {N}개 규칙, {M}개 스킬

### Critical
- [규칙명] {요약} `severity:critical / regression:none / scope:harness-only`
  - 단절: {설명}
  - 위임 후보: {Phase 4 매트릭스 매칭}

### Warning
- ...

### Info
- ...

### 통과 항목: {K}개 (생략)
```

## Phase 4: 위임 매트릭스 (직접 보강 금지)

본 스킬은 **위임 경로 제시까지만** 수행한다. 사용자 승인을 받으면 매트릭스에 정의된 SSOT 스킬을 호출하여 작업을 넘긴다. 본 스킬 세션 안에서 직접 코드/설정/스킬 본문을 편집하지 않는다.

### 위임 매트릭스

각 행은 (severity, regression-risk, scope) 3축을 모두 명시한다. 매칭 우선순위: 위에서 아래로 첫 일치 행을 채택. 한 항목이 여러 행에 부합하면 위(더 보수적인) 행을 적용.

| severity | regression-risk | scope | 위임 경로 | 사유 |
|----------|-----------------|-------|----------|------|
| `*` | `high` | `framework-core` | **사용자 직접 결정 필요** | 프레임워크 동작 변경, 자동 위임 금지 (severity 무관) |
| `critical \| warning` | `medium` | `code-and-policy` | `/plan-issues` (ADR 동반) → `/autopilot` | 정책 결정 동반, 마일스톤 단위 분해 |
| `critical \| warning` | `low` | `config-only` | `/plan-issues` → `/process-ticket` | 단일 이슈 단위 빌드 설정 변경, 패키지 단위 검증 필요 |
| `critical \| warning` | `none` | `harness-only` | `/optimize-harness` (1줄 정정 묶음) | 회귀 위험 0의 포인터·라벨 정정 자동 묶음 처리 |
| `info` | `none` | `harness-only` | `/optimize-harness` | 문서·라벨 정리 |

**정규화 규칙**:
- 위 매트릭스에 매칭되지 않는 조합은 한 단계 더 보수적인 가까운 행으로 라우팅 (예: `critical / medium / framework-core`는 1행 적용 → 사용자 결정 필요).
- `severity:info / regression:>none` 조합은 발생하지 않음 — info는 정의상 동작 변경 없음. 발생 시 분류 오류이므로 재분류한다.

### 사용자 응답에 따른 분기

발견 항목들을 위 매트릭스로 분류한 뒤 사용자에게 보고하고 다음 중 하나로 응답을 받는다:

- **"위임"**: 분류별로 적합한 SSOT 스킬을 호출 (한 세션에 여러 SSOT 병렬 호출 가능, 단 본 스킬은 즉시 종료)
- **"이슈만 등록"**: GitHub 이슈로 등록 후 종료. `/plan-issues` 또는 `gh issue create` 사용
- **"무시"**: 보고만 남기고 종료. 보고서를 `.claude/evaluations/{date}.md`로 보존 (선택). 디렉토리가 없으면 `mkdir -p .claude/evaluations`로 생성한 후 작성

사용자가 "전부 자동으로", "알아서 해" 등으로 응답해도 본 스킬은 **위임 매트릭스 적용**까지만 자동 진행하며, **`framework-core` 또는 `regression:high` 항목은 명시적 사용자 결정 없이 위임하지 않는다**. 이는 charter §4-A·§1의 직접 적용이다.

### 모두 통과

- **모두 통과**: 1줄 보고 ("Evaluate Harness: {N}개 검사 모두 통과") 후 종료.

---

## 규칙

- 메인 에이전트는 **검증 대상 코드를 직접 평가하지 않는다.** 외부 서브에이전트만이 평가 권한을 가진다 (자기확증 편향 차단).
- 서브에이전트는 `Explore` 또는 `general-purpose`만 사용. 코드 수정 권한 없는 에이전트로 한정.
- 평가 결과는 **차단 선언과 실제 차단의 갭**만 보고한다. 신규 규칙 제안은 본 스킬 본분 밖.
- Phase 2 병렬 spawn은 동일 메시지에서 다중 Agent 호출로 수행한다.
- **Phase 4 직접 보강 금지**: 본 스킬 세션에서 `Edit`/`Write` 도구로 `pyproject.toml`·`settings.json`·`.claude/rules/*`·`.claude/skills/*` 본문을 수정하지 않는다. 위임만 한다.
- Phase 4의 `evaluations/` 보고서 보존은 예외 (보고는 본분 안).

$ARGUMENTS
