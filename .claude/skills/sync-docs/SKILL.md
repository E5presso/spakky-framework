---
name: sync-docs
description: 코드 변경 후 관련 문서를 코드 기반으로 동기화합니다. 대상에 따라 개발 문서(sync-dev-docs) 또는 사용자 문서(sync-user-docs)로 라우팅합니다.
argument-hint: "[dev|user|all] [패키지명]"
user-invocable: true
---

# Sync Docs — 문서 동기화 라우터

코드 변경 사항을 감지하여 관련 문서를 **코드 기반으로** 동기화한다. 기존 문서의 불일치를 수정하고, **코드에는 존재하지만 문서에 없는 항목을 감지하여 신규 문서를 생성하거나 기존 문서에 섹션을 추가한다.** 변경 범위에 따라 적절한 서브 스킬을 호출한다.

## 대상 구분

| 스킬 | 대상 독자 | 동기화 문서 |
|------|----------|-----------|
| `/sync-dev-docs` | 프레임워크 **개발자** | ARCHITECTURE.md, 패키지 README.md, CONTRIBUTING.md, docs/adr/README.md |
| `/sync-user-docs` | 프레임워크 **사용자** | docs/guides/, docs/api/, docs/index.md, docs/glossary.md, mkdocs.yml 등 |

## 사용법

```
/sync-docs                    # 변경 범위에서 자동 판단하여 해당 서브 스킬 실행
/sync-docs dev                # 개발 문서만 동기화
/sync-docs user               # 사용자 문서만 동기화
/sync-docs all                # 양쪽 모두 동기화
/sync-docs dev spakky-event   # 개발 문서 중 특정 패키지만
/sync-docs user spakky-event  # 사용자 문서 중 특정 패키지만
```

---

## 라우팅 로직

### Step 1: 인자 파싱

- 첫 번째 인자가 `dev`, `user`, `all` 중 하나면 → 해당 대상으로 고정
- 첫 번째 인자가 패키지명이면 → Step 2로 진행 (자동 판단)
- 인자 없으면 → Step 2로 진행 (자동 판단)

### Step 2: 변경 범위에서 자동 판단

```bash
git diff --name-only HEAD~1..HEAD
# 또는 커밋 전이면:
git diff --name-only
git diff --cached --name-only
```

변경된 파일 경로를 분석하여 라우팅:

| 변경 파일 패턴 | 라우팅 대상 |
|--------------|-----------|
| `core/*/src/**`, `plugins/*/src/**` (소스 코드) | **양쪽 모두** — 개발 문서와 사용자 문서 모두 영향 |
| `core/*/pyproject.toml`, `plugins/*/pyproject.toml` | **양쪽 모두** — 의존성·패키지 구조 변경 |
| `docs/guides/**`, `docs/api/**`, `docs/index.md`, `docs/glossary.md`, `mkdocs.yml` | **user만** — 사용자 문서 자체 수정 |
| `ARCHITECTURE.md`, `CONTRIBUTING.md`, `core/*/README.md`, `plugins/*/README.md` | **dev만** — 개발 문서 자체 수정 |
| `docs/adr/**` | **dev만** — ADR은 개발 문서 범위 |
| 도구/설정 파일만 변경 | **dev만** — CONTRIBUTING.md 검증 |

### Step 2.5: 서브 스킬 SKILL.md Read

라우팅 대상이 결정되면, 해당 서브 스킬의 SKILL.md를 Read하여 내용을 확보한다. Step 3에서 서브에이전트 프롬프트를 구성할 때 이 내용을 인라인으로 포함해야 하므로, 이 단계에서 미리 읽어둔다.

- dev 대상 → `.claude/skills/sync-dev-docs/SKILL.md` Read
- user 대상 → `.claude/skills/sync-user-docs/SKILL.md` Read
- all → 양쪽 모두 Read

### Step 3: Write → Review 수렴 루프 (대상별)

판단된 각 대상(dev/user)에 대해 **Write → Review 수렴 루프**를 실행한다. dev와 user는 서로 다른 파일을 수정하므로 **백그라운드 병렬** 실행한다.

메인 에이전트는 **순수 오케스트레이터** — 직접 문서를 수정하거나 검증하지 않는다. 두 서브에이전트의 실행과 피드백 전달만 담당한다.

> **원칙**: 비용을 고려하지 않는다. Review 에이전트가 더 이상 지적할 것이 없을 때까지 반복한다.
> **핵심**: 서브 스킬의 SKILL.md는 서브에이전트에 자동 로드되지 않는다. 라우터가 Step 2.5에서 Read한 SKILL.md 내용을 서브에이전트 프롬프트에 **인라인으로 직접 포함**한다.

#### 3-0. 서브에이전트 역할 분리

> **서브에이전트 요구사항**:
> - **Write 에이전트**: 파일 수정 권한(read + write) 필수. 읽기 전용 에이전트로는 수렴 루프가 동작하지 않는다.
> - **모델 수준**: Write/Review 모두 메인 에이전트와 동등 수준의 모델을 사용한다. 저성능 모델은 문서 작성·검증 품질이 부족하다.

| 역할 | 실행 방식 | 담당 |
|------|----------|------|
| **오케스트레이터** (메인) | 메인 컨텍스트 | 루프 제어, 피드백 전달, 수렴 판정, 결과 통합 |
| **Write 에이전트** | 서브에이전트 (read + write) | Phase 1 (변경 감지) + Phase 2 (문서 작성/수정). 이전 라운드 피드백 반영 |
| **Review 에이전트** | 서브에이전트 (fresh context, read-only 가능) | Phase 3 (팩트체크). Write 결과를 독립적·적대적으로 검증 |

Write와 Review는 **반드시 별도 서브에이전트**로 실행한다. 같은 컨텍스트에서 작성과 검증을 수행하면 self-confirmation bias가 발생한다.

#### 3-1. 수렴 루프 알고리즘

```python
review_history: list[ReviewResult] = []
round = 1

while True:
    # ── Write ──
    write_result = call_write_subagent(
        phases=Phase_1 + Phase_2,       # 서브 스킬 SKILL.md에서 인라인
        previous_reviews=review_history, # 모든 이전 라운드의 리뷰 피드백
        round=round,
    )

    # ── Review (fresh context) ──
    review_result = call_review_subagent(
        phases=Phase_3,                  # 서브 스킬 SKILL.md에서 인라인
        modified_files=write_result.files,
        coverage_matrix=write_result.matrix,
        source_packages=[변경된 패키지 경로],
    )

    # ── 수렴 판정 ──
    actionable = count(review_result, severity in {Critical, Warning})

    if actionable == 0:
        break  # 수렴 완료

    if same_issues_repeated(review_history, review_result, threshold=3):
        mark_as_unresolved(review_result)
        break  # 고착 탈출

    # ── 피드백 축적 ──
    review_history.append(review_result)
    round += 1
```

**종료 조건** (우선순위 순):

1. **수렴**: Critical + Warning = 0건 → 성공 종료
2. **고착**: 동일 이슈가 3라운드 연속 반복 → 미해결로 보고 후 종료
3. **라운드 제한 없음**: 수렴 또는 고착이 유일한 종료 조건이다

> Info, 미확인 이슈는 수렴 판정에서 제외한다. 최종 결과에만 포함한다.

#### 3-2. Write 서브에이전트 프롬프트

프롬프트에 인라인으로 포함할 내용:

| 항목 | 내용 |
|------|------|
| Phase 내용 | 서브 스킬 SKILL.md의 **Phase 1 + Phase 2 전문** + 규칙 섹션 |
| 패키지명 | 인자로 받은 패키지명 (있는 경우) |
| 라운드 번호 | 현재 라운드 (`round`) |
| 이전 리뷰 피드백 | `review_history` 전체 — **모든** 이전 라운드의 이슈 목록 |

**라운드 1**: 이전 리뷰 없이 순수 동기화 수행.
**라운드 2+**: 프롬프트에 아래 지시를 추가한다:

```
이전 {N}회 라운드에서 Review 에이전트가 다음 이슈를 지적했습니다.
반드시 모든 Critical/Warning 이슈를 수정하세요.
이전에 수정했으나 재지적된 이슈는 접근 방식을 바꿔 수정하세요.

{review_history 전문}
```

**Write 출력 형식 (필수)**:

```
수정/생성 파일 목록:
- {경로}: {변경 요약}

커버리지 매트릭스:
{Phase 1에서 생성한 매트릭스}
```

#### 3-3. Review 서브에이전트 프롬프트

**반드시 fresh context 서브에이전트**로 실행한다 (Write와 동일 컨텍스트 금지).

프롬프트에 인라인으로 포함할 내용:

| 항목 | 내용 |
|------|------|
| Phase 내용 | 서브 스킬 SKILL.md의 **Phase 3 전문** (체크리스트 포함) |
| Write 결과 | 수정/생성된 파일 경로 목록 |
| 커버리지 매트릭스 | Write가 출력한 매트릭스 |
| 소스 패키지 경로 | 변경된 패키지의 `src/` 경로 |

**Review 에이전트 행동 지침** (프롬프트에 반드시 명시):

```
당신은 적대적 검증자입니다. Write 에이전트의 결과를 신뢰하지 마세요.

1. Phase 3의 모든 체크리스트 항목을 빠짐없이 순회하세요.
   이슈가 없어도 "순회 완료"를 명시하세요.
2. 문서의 코드 블록을 하나도 빠짐없이 실제 소스 파일과 대조하세요.
3. import 경로, 클래스 시그니처, 데코레이터 파라미터를 한 글자도
   신뢰하지 않고 실제 .py 파일을 Read하여 검증하세요.
4. 코드에 존재하지만 문서에 누락된 항목도 지적하세요.
5. "아마 맞을 것이다"로 넘어가지 마세요. 확인할 수 없으면 [미확인]으로 보고하세요.
```

**Review 출력 형식 (필수)**:

```
이슈 목록:
- [Critical] {경로}:{라인} — {설명}
- [Warning] {경로}:{라인} — {설명}
- [Info] {경로}:{라인} — {설명}
- [미확인] {경로}:{라인} — {설명}

체크리스트 순회 결과:
- {영역}: {N}개 검증, {M}개 이슈

이슈 없음 시: "모든 체크리스트를 순회하였으며, 이슈가 없습니다."
```

### Step 4: 교차 검증 루프

**양쪽 대상의 수렴 루프가 모두 완료된 후** 실행한다. dev와 user 문서 간 정합성을 검증한다.

**교차 검증은 텍스트 요약이 아닌, 실제 파일을 Read하여 수행한다.** 서브에이전트 결과 요약만으로 판단하면 누락이 발생한다.

```
반복:
  1. 양쪽 서브에이전트 결과에서 수정/생성된 파일 경로 목록 수집
  2. 수정된 파일을 직접 Read하여 실제 내용을 확인
  3. 교차 영향 체크리스트를 순회:
     - ARCHITECTURE.md 패키지 테이블 ↔ docs/index.md 패키지 테이블 일치?
     - ARCHITECTURE.md 의존성 그래프 ↔ docs/index.md 의존성 그래프 일치?
     - 신규 생성된 가이드 → mkdocs.yml nav에 반영? docs/index.md 튜토리얼 테이블에 반영?
     - 패키지 README Features ↔ docs/guides/ 해당 가이드의 기능 설명 일치?
     - 신규 추가된 용어/개념 → docs/glossary.md에 반영?
     - 에러 클래스 추가 → docs/error-hierarchy.md에 반영?
  4. 불일치 발견 시 해당 파일을 직접 수정
  5. 불일치 0건이면 루프 종료
  6. 동일 불일치가 3회 반복되면 미해결로 보고 후 종료
```

### Step 5: 결과 통합

수렴 루프 완료 후 결과를 통합하여 보고한다.

```
## 문서 동기화 결과

### 개발 문서 (sync-dev-docs)

{sync-dev-docs 결과}

### 사용자 문서 (sync-user-docs)

{sync-user-docs 결과}

### 교차 검증

- 교차 검증 라운드: {N}회
- 추가 수정: {M}건
- 미해결: {K}건 (해당 시)
```

---

## 규칙

- **Code-first**: 모든 문서는 실제 코드 기반으로 검증한다.
- **CHANGELOG.md는 수정하지 않는다** — 자동 생성 대상.
- **오케스트레이터는 직접 문서를 수정하지 않는다** — Write/Review에 위임한다.
- **Write와 Review는 반드시 별도 서브에이전트**로 실행한다 — self-confirmation bias 방지.
- **비용 무시**: 정확성이 최우선. 라운드 수를 줄이기 위해 검증을 생략하지 않는다.
- dev/user 수렴 루프는 **독립 병렬** 실행한다 — 한쪽의 수렴이 다른 쪽을 블로킹하지 않는다.
- 양쪽 스킬이 같은 파일을 수정할 일은 없으므로 병렬 실행 안전.

$ARGUMENTS
