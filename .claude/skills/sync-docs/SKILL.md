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

### Step 3: Write/Verify 오케스트레이션 (대상별)

판단된 각 대상(dev/user)에 대해 **Write → Verify 수렴 루프**를 실행한다. dev와 user는 서로 다른 파일을 수정하므로 **백그라운드 병렬** 실행한다.

> **핵심**: 서브 스킬의 SKILL.md는 서브에이전트에 자동 로드되지 않는다. 라우터가 Step 2에서 서브 스킬 SKILL.md를 Read한 상태이므로, 필요한 Phase 내용을 서브에이전트 프롬프트에 **인라인으로 직접 포함**하여 전달해야 한다.

#### 3-1. Write 서브에이전트 프롬프트 구성

서브에이전트 프롬프트에 다음 내용을 **인라인으로** 포함한다 (라우터가 이미 Read한 서브 스킬 SKILL.md에서 해당 섹션을 복사):

**dev 대상:**
- sync-dev-docs Phase 1 (변경 감지 + 커버리지 매트릭스) 전문
- sync-dev-docs Phase 2 (문서별 동기화) 전문
- sync-dev-docs 규칙 섹션
- 패키지명 인자 (있는 경우)
- 이전 라운드 Verify 이슈 목록 (라운드 2+ 인 경우)

**user 대상:**
- sync-user-docs Phase 1 (변경 감지 + 커버리지 매트릭스) 전문
- sync-user-docs Phase 2 (문서별 동기화) 전문
- sync-user-docs 규칙 섹션 (할루시네이션 제로 원칙 포함)
- 패키지명 인자 (있는 경우)
- 이전 라운드 Verify 이슈 목록 (라운드 2+ 인 경우)

**Write 출력 형식 (필수)** — 프롬프트에 이 형식을 명시한다:

```
수정/생성 파일 목록:
- {경로}: {변경 요약}

커버리지 매트릭스:
{Phase 1에서 생성한 매트릭스 전문}
```

#### 3-2. Verify 서브에이전트 프롬프트 구성

Write 완료 후, **별도의 fresh context 서브에이전트**로 Verify를 실행한다. 같은 에이전트에서 Write와 Verify를 실행하면 self-confirmation bias가 발생하므로 반드시 분리한다.

**dev 대상:**
- sync-dev-docs Phase 3 (검증) 전문
- Write가 출력한 수정/생성 파일 경로 목록
- Write가 출력한 커버리지 매트릭스
- 변경된 소스 코드 패키지 경로

**user 대상:**
- sync-user-docs Phase 3 (편집증적 팩트체크) 전문 (3-1 ~ 3-8 체크리스트 포함)
- Write가 출력한 수정/생성 파일 경로 목록
- Write가 출력한 커버리지 매트릭스
- 변경된 소스 코드 패키지 경로

**Verify 출력 형식 (필수)** — 프롬프트에 이 형식을 명시한다:

```
이슈 목록:
- [Critical] {경로}:{라인} — {설명}
- [Warning] {경로}:{라인} — {설명}
- [Info] {경로}:{라인} — {설명}
- [미확인] {경로}:{라인} — {설명}

체크리스트 순회 결과:
- {항목}: {N}개 검증, {M}개 이슈
```

#### 3-3. 수렴 판정

```
라운드 = 1
반복:
  1. Write 서브에이전트 호출 (Agent tool)
  2. Write 완료 후 Verify 서브에이전트 호출 (별도 Agent tool — fresh context)
  3. Verify 결과에서 Critical + Warning 이슈 수 집계 (Info, 미확인은 제외)
  4. 이슈 0건 → 루프 종료
  5. 이슈 > 0건 → 이슈 목록을 다음 라운드 Write에 전달
  6. 라운드 += 1
  최대 반복: 3회 (무한 루프 방지)
  3회 후에도 미해결 이슈가 있으면 "미해결" 섹션으로 보고한다.
```

dev와 user를 모두 실행하는 경우, 각 대상의 Write/Verify 루프를 **독립적으로 병렬** 실행한다. 한쪽의 수렴이 다른 쪽을 블로킹하지 않는다.

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

  최대 반복: 3회 (무한 루프 방지)
  3회 후에도 미해결 이슈가 있으면 결과 보고에 "미해결" 섹션으로 남긴다.
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
- 스킬 실행은 **서브에이전트(백그라운드)**로 수행하여 컨텍스트를 분리하고 메인 컨텍스트를 블로킹하지 않는다.
- 양쪽 스킬이 같은 파일을 수정할 일은 없으므로 병렬 실행 안전.

$ARGUMENTS
