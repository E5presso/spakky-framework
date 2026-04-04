---
name: sync-docs
description: 코드 변경 후 관련 문서를 코드 기반으로 동기화합니다. 대상에 따라 개발 문서(sync-dev-docs) 또는 사용자 문서(sync-user-docs)로 라우팅합니다.
argument-hint: "[dev|user|all] [패키지명]"
user-invocable: true
---

# Sync Docs — 문서 동기화 라우터

코드 변경 사항을 감지하여 관련 문서를 **코드 기반으로** 동기화한다. 변경 범위에 따라 적절한 서브 스킬을 호출한다.

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

### Step 3: 스킬 실행

판단된 대상에 따라 독립 스킬을 **서브에이전트**로 호출한다.

- **dev만**: `/sync-dev-docs` 서브에이전트 1개 실행
- **user만**: `/sync-user-docs` 서브에이전트 1개 실행
- **양쪽 모두**: `/sync-dev-docs`와 `/sync-user-docs` 서브에이전트를 **병렬** 실행

패키지명 인자가 있으면 스킬에 전달한다.

### Step 4: 결과 통합

각 서브에이전트의 결과를 통합하여 보고한다.

```
## 문서 동기화 결과

### 개발 문서 (sync-dev-docs)

{sync-dev-docs 결과}

### 사용자 문서 (sync-user-docs)

{sync-user-docs 결과}
```

---

## 규칙

- **Code-first**: 모든 문서는 실제 코드 기반으로 검증한다.
- **CHANGELOG.md는 수정하지 않는다** — 자동 생성 대상.
- 스킬 실행은 **서브에이전트**로 수행하여 컨텍스트를 분리한다.
- 양쪽 스킬이 같은 파일을 수정할 일은 없으므로 병렬 실행 안전.

$ARGUMENTS
