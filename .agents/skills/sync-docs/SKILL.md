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

- dev 대상 → `.agents/skills/sync-dev-docs/SKILL.md` Read
- user 대상 → `.agents/skills/sync-user-docs/SKILL.md` Read
- all → 양쪽 모두 Read

### Step 3: Write → Review 수렴 루프 (대상별)

판단된 각 대상(dev/user)에 대해 **Write → Review 수렴 루프**를 실행한다. dev와 user는 파일 소유가 분리되므로 백그라운드 병렬 실행한다. 메인은 오케스트레이터이며 직접 문서를 수정하지 않는다.

필수 불변식:
- 라우터가 Step 2.5에서 읽은 서브 스킬 SKILL.md 내용을 Write/Review 프롬프트에 인라인 포함한다.
- Write는 read+write 권한, Review는 fresh context에서 적대적 read-only 검증. 같은 컨텍스트 금지.
- 비용 절감으로 라운드를 줄이지 않는다. Critical/Warning 0건 또는 동일 이슈 3회 반복만 종료 조건이다.
- 동일 이슈가 2라운드 이상 반복되면 메인이 분쟁 대상 코드와 규칙을 직접 읽어 Writer/Verifier 중 누구도 자동 채택하지 않고 판정한다.

Write 프롬프트 입력/출력:

| 입력 | 출력 |
|------|------|
| 서브 스킬 Phase 1+2+규칙, 패키지명, 라운드 번호, 모든 이전 Review 피드백 | 수정/생성 파일 목록, 커버리지 매트릭스 |

Review 프롬프트 입력/출력:

| 입력 | 출력 |
|------|------|
| 서브 스킬 Phase 3 전체, Write 결과 파일 목록, 커버리지 매트릭스, 변경 패키지 `src/` 경로 | `[Critical|Warning|Info|미확인] 경로:라인 — 설명`, 체크리스트 순회 결과 |

Review 프롬프트에는 반드시 다음을 포함한다: Write 결과를 신뢰하지 말 것, 모든 체크리스트 순회, 모든 코드 블록과 import/시그니처/데코레이터 파라미터를 실제 `.py` 파일로 대조, 코드에는 있으나 문서에 없는 항목 지적, 확인 불가 시 `[미확인]` 보고. 이슈가 없어도 "모든 체크리스트를 순회하였으며, 이슈가 없습니다."를 출력한다.

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
  4. 불일치 발견 시 메인이 직접 수정하지 않고, 해당 대상(dev/user)의 Step 3 Write → Review 루프에 피드백으로 투입
  5. 양쪽 수렴 완료 후 Step 4를 다시 실행
  6. 불일치 0건이면 루프 종료
  7. 동일 불일치가 3회 반복되면 미해결로 보고 후 종료
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

- **작성 규칙**: 모든 동기화 문서(서브 스킬 포함)는 [doc-format.md](doc-format.md)의 포맷·문서별 규칙·Verifier 10항목 체크리스트를 따른다. 서브에이전트 프롬프트에 해당 섹션을 인라인으로 포함한다.
- **Code-first**: 모든 문서는 실제 코드 기반으로 검증한다.
- **CHANGELOG.md는 수정하지 않는다** — 자동 생성 대상.
- **오케스트레이터는 직접 문서를 수정하지 않는다** — Write/Review에 위임한다.
- **Write와 Review는 반드시 별도 서브에이전트**로 실행한다 — self-confirmation bias 방지.
- **비용 무시**: 정확성이 최우선. 라운드 수를 줄이기 위해 검증을 생략하지 않는다.
- dev/user 수렴 루프는 **독립 병렬** 실행한다 — 한쪽의 수렴이 다른 쪽을 블로킹하지 않는다.
- 양쪽 스킬이 같은 파일을 수정할 일은 없으므로 병렬 실행 안전.

$ARGUMENTS
