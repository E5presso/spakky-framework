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

### Step 3: 스킬 실행 (수렴 루프)

판단된 대상에 따라 독립 스킬을 **서브에이전트(백그라운드)**로 호출한다. `run_in_background: true`로 실행하여 메인 컨텍스트를 블로킹하지 않는다.

- **dev만**: `/sync-dev-docs` 서브에이전트 1개 백그라운드 실행
- **user만**: `/sync-user-docs` 서브에이전트 1개 백그라운드 실행
- **양쪽 모두**: `/sync-dev-docs`와 `/sync-user-docs` 서브에이전트를 **백그라운드 병렬** 실행

패키지명 인자가 있으면 스킬에 전달한다.

### Step 4: 교차 검증 루프

각 서브에이전트 완료 후, **다른 서브에이전트가 수정한 문서도 포함하여** 전체 정합성을 재검증한다. 이는 서브 스킬 내부의 자체 수렴 루프와 별개로, 서브 스킬 간 교차 영향을 잡기 위한 것이다.

**교차 검증은 텍스트 요약이 아닌, 실제 파일을 Read하여 수행한다.** 서브에이전트 결과 요약만으로 판단하면 누락이 발생한다.

```
반복:
  1. 서브에이전트 결과에서 수정/생성된 파일 경로 목록 수집
  2. 수정된 파일을 직접 Read하여 실제 내용을 확인
  3. 교차 영향 체크리스트를 순회:
     - ARCHITECTURE.md 패키지 테이블 ↔ docs/index.md 패키지 테이블 일치?
     - ARCHITECTURE.md 의존성 그래프 ↔ docs/index.md 의존성 그래프 일치?
     - 신규 생성된 가이드 → mkdocs.yml nav에 반영? docs/index.md 튜토리얼 테이블에 반영?
     - 패키지 README Features ↔ docs/guides/ 해당 가이드의 기능 설명 일치?
     - 신규 추가된 용어/개념 → docs/glossary.md에 반영?
     - 에러 클래스 추가 → docs/error-hierarchy.md에 반영?
  4. 불일치 발견 시 해당 파일을 직접 수정하거나, 해당 서브 스킬을 **수정된 파일만 대상으로** 재실행
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
