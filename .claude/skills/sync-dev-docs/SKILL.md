---
name: sync-dev-docs
description: 코드 변경 후 프레임워크 개발 문서(ARCHITECTURE.md, 패키지 README.md, CONTRIBUTING.md)를 코드 기반으로 동기화합니다.
argument-hint: "[패키지명]"
user-invocable: false
---

# Sync Dev Docs — 개발 문서 동기화

코드 변경 사항을 감지하여 프레임워크 **개발자** 대상 문서를 **코드 기반으로** 동기화한다. 문서에 코드와 맞지 않는 내용이 있으면 수정하고, 새로 추가된 공개 인터페이스는 문서에 반영한다. **코드에는 존재하지만 문서에 없는 항목을 감지하여 신규 문서를 생성하거나 기존 문서에 섹션을 추가한다.**

> **원칙**: Code > CONTRIBUTING.md > CLAUDE.md > README.md. 불일치 시 문서를 코드에 맞춘다.

## 대상 문서

- `core/*/README.md`, `plugins/*/README.md` — 패키지별 개발 안내
- `ARCHITECTURE.md` — 아키텍처 개요, 패키지 구조 테이블, 의존성 그래프
- `CONTRIBUTING.md` — 기여 가이드, 개발 환경 설정
- `docs/adr/README.md` — ADR 목록 및 상태

---

## Phase 1: 변경 감지 + 커버리지 매트릭스

### 1-1. 변경 범위 결정

```bash
git diff --name-only HEAD~1..HEAD
# 또는 커밋 전이면:
git diff --name-only
git diff --cached --name-only
```

변경된 파일에서 영향받는 패키지를 추출한다.

### 1-2. 커버리지 매트릭스 (필수)

변경 유형 분류 **전에**, 전체 패키지 대비 개발 문서 커버리지를 점검한다. 이 단계는 "변경된 패키지"뿐 아니라 **기존에 누락된 문서**도 감지하기 위한 것이다.

```bash
# 1. 전체 패키지 목록 수집
ls -d core/*/src plugins/*/src | sed 's|/src||' | sort

# 2. 개발 문서 커버리지 대조 — 각 패키지에 대해 아래 존재 여부 확인
#    - {core|plugins}/{패키지명}/README.md (패키지 README)
#    - ARCHITECTURE.md 패키지 구조 테이블에 해당 패키지 행 존재
#    - ARCHITECTURE.md 의존성 그래프에 해당 패키지 노드 존재
#    - ARCHITECTURE.md 관련 섹션에 해당 패키지 컴포넌트 설명 존재
#    - CONTRIBUTING.md commit scope에 해당 패키지 존재
```

**커버리지 매트릭스 출력 형식:**

| 패키지 | README | ARCH 테이블 | ARCH 그래프 | ARCH 섹션 | CONTRIB scope |
|--------|--------|-----------|-----------|----------|--------------|
| spakky | O | O | O | O | O |
| spakky-opentelemetry | O | O | O | **X** | O |
| ... | ... | ... | ... | ... | ... |

**X 표시된 항목은 Phase 2에서 반드시 동기화 대상에 포함한다.** 변경된 패키지가 아니더라도, 커버리지 매트릭스에서 누락이 발견되면 동기화 대상이다.

### 1-3. 변경 유형 분류

변경된 파일을 아래 카테고리로 분류한다:

| 카테고리 | 패턴 | 동기화 대상 |
|---------|------|-----------|
| **공개 인터페이스 변경** | ABC/Protocol 추가·수정·삭제, `__all__` 변경 | 패키지 README, ARCHITECTURE.md |
| **패키지 추가·삭제** | `pyproject.toml` 신규, 패키지 디렉토리 추가·삭제 | ARCHITECTURE.md (패키지 구조 테이블, 의존성 그래프) |
| **의존성 변경** | `pyproject.toml`의 dependencies 변경 | ARCHITECTURE.md (의존성 그래프) |
| **데코레이터·스테레오타입 변경** | `@Component`, `@Bean` 등의 시그니처 변경 | 패키지 README (Quick Start, Features) |
| **설정·환경 변경** | 개발 도구, 빌드 설정 변경 | CONTRIBUTING.md |
| **ADR 추가** | `docs/adr/` 파일 추가 | ARCHITECTURE.md (ADR 테이블) |
| **문서 커버리지 누락** | 1-2 매트릭스에서 X로 표시된 항목 | 해당 문서 신규 생성 또는 기존 문서에 섹션 추가 |

코드와 이미 일치하는 카테고리는 건너뛴다.

## Phase 2: 문서별 동기화 (Write 에이전트)

각 문서를 **병렬 서브에이전트**로 동기화한다. 같은 파일을 동시에 수정하지 않으므로 충돌 없음.

> **중요**: Phase 2는 "Write 에이전트"가 담당한다. Phase 3 검증은 **별도의 "Verify 에이전트"**가 fresh context에서 수행하여 self-confirmation bias를 방지한다.

### 2-1. 패키지 README.md

**대상**: 변경된 패키지의 `core/*/README.md` 또는 `plugins/*/README.md`

서브에이전트에게 전달할 컨텍스트:
- 변경된 파일 목록과 diff
- 현재 README.md 내용
- 패키지의 `src/` 디렉토리에서 공개 인터페이스 목록

**검증 항목**:

1. **Features 섹션**: 공개 클래스/데코레이터 목록이 코드와 일치하는가
2. **Quick Start 섹션**: 코드 예시의 import 경로가 유효한가
3. **Installation 섹션**: 패키지명이 `pyproject.toml`의 `[project] name`과 일치하는가
4. **API 설명**: 클래스/함수 시그니처가 코드와 일치하는가

**동기화 규칙**:
- 코드에서 제거된 API는 README에서도 제거
- 코드에서 추가된 공개 API는 README에 추가 (기존 섹션 스타일에 맞춰)
- import 경로 변경은 README의 모든 코드 블록에서 일괄 수정
- **README가 없는 패키지는 기존 패키지 README 스타일을 참고하여 신규 생성**
- **CHANGELOG.md는 수정하지 않는다** (자동 생성)

### 2-2. ARCHITECTURE.md

**검증 항목**:

1. **패키지 구조 테이블**: 패키지 목록과 역할 설명이 코드와 일치하는가
2. **의존성 그래프 (Mermaid)**: 노드와 엣지가 실제 `pyproject.toml` 의존성과 일치하는가
3. **각 섹션 설명**: 코어/플러그인 설명이 현재 코드의 구조와 일치하는가
4. **ADR 테이블**: `docs/adr/` 디렉토리의 ADR 파일 목록과 일치하는가

**의존성 그래프 검증 방법**:

```bash
# 실제 패키지 간 의존성 추출
grep -A 20 "\[project\]" core/*/pyproject.toml plugins/*/pyproject.toml | grep "spakky"
```

그래프의 엣지를 실제 의존성과 교차 대조하여 누락/잉여 엣지를 찾는다.

**동기화 규칙**:
- Mermaid 다이어그램은 `mermaid.md` 규칙을 따른다
- 패키지 추가 시 테이블 행과 그래프 노드를 추가
- 패키지 삭제 시 테이블 행과 그래프 노드·엣지를 제거
- **코드에 존재하지만 ARCHITECTURE.md에 누락된 패키지·모듈·의존성은 신규 추가**

### 2-3. CONTRIBUTING.md

**검증 항목**:

1. **Development Setup**: 설치 명령어가 현재 환경과 일치하는가
2. **Running Tests**: 테스트 실행 명령어가 유효한가
3. **패키지 구조 설명**: 디렉토리 구조가 현재와 일치하는가

변경된 카테고리가 "설정·환경 변경"일 때만 검증한다.

### 2-4. docs/adr/README.md

ADR 파일이 추가·변경된 경우에만:

1. ADR 목록 테이블이 `docs/adr/` 디렉토리의 파일과 일치하는가
2. ADR 상태(Accepted, Superseded 등)가 파일 내용과 일치하는가

## Phase 3: 검증 (Verify 에이전트 — 별도 서브에이전트)

> **Phase 2와 Phase 3은 반드시 서로 다른 서브에이전트에서 실행한다.** Write 에이전트가 수정한 문서를 같은 컨텍스트에서 검증하면 self-confirmation bias가 발생한다. Verify 에이전트는 fresh context에서 수정된 문서를 코드와 독립적으로 대조한다.

Verify 에이전트에게 전달할 컨텍스트:
- Phase 2에서 수정/생성된 문서 파일 경로 목록
- 변경된 소스 코드 패키지 경로

### 3-1. 링크 검증

수정된 문서 내의 내부 링크(파일 경로, 앵커)가 유효한지 확인한다:

- 파일 참조: `[text](path/to/file)` → 파일 존재 여부
- 앵커 참조: `[text](#section)` → 섹션 존재 여부

### 3-2. 코드 블록 검증

README의 코드 블록에 포함된 import 경로가 실제로 존재하는지 확인한다:

```bash
# README에서 import 문 추출 후 실제 모듈 존재 확인
grep -oP "from \S+" <README.md> | sort -u
```

## Phase 4: 수렴 루프 (Write → Verify 분리 실행)

Phase 2(Write)와 Phase 3(Verify)는 **반드시 별도의 서브에이전트 호출**로 분리한다. 같은 에이전트 안에서 Write 후 Verify를 실행하면 self-confirmation bias가 발생하므로, **호출자(이 스킬을 실행하는 에이전트)가 루프를 오케스트레이션**한다.

```
라운드 = 1
반복:
  1. Write 서브에이전트 호출 (Agent tool):
     - 입력: Phase 1 결과 (커버리지 매트릭스 + 변경 유형) + 이전 라운드 이슈 목록
     - 작업: Phase 2 실행 (동기화 — 수정 + 신규 생성)
     - 출력: 수정/생성한 파일 경로 목록과 변경 요약
  
  2. Write 완료 대기 후, Verify 서브에이전트 호출 (별도 Agent tool — fresh context):
     - 입력: Write가 수정/생성한 파일 경로 목록 + Phase 3 체크리스트 전문
     - 작업: Phase 3 실행 (검증)
     - 출력: 이슈 목록 (심각도별 분류)
  
  3. Verify 결과에서 이슈 수 집계
  4. 이슈 0건이면 → 루프 종료, Phase 5로
  5. 이슈 > 0건이면 → 이슈 목록을 다음 Write 에이전트에 전달, 다음 라운드
  6. 라운드 += 1

  최대 반복: 3회 (무한 루프 방지)
  3회 후에도 미해결 이슈가 있으면 "미해결" 섹션으로 보고한다.
```

**핵심**: 호출자가 `Agent` 도구를 2번 순차 호출한다 — Write 1회, Verify 1회. 이것이 1라운드이다. Verify에서 이슈가 나오면 다시 Write → Verify로 2라운드를 시작한다.

## Phase 5: 결과 보고

```
## 개발 문서 동기화 결과

### 변경된 문서

| 문서 | 변경 내용 | 카테고리 |
|------|----------|---------|
| {경로} | {변경 요약} | {인터페이스/의존성/설정/ADR} |

### 검증

- 수렴 라운드: {N}회
- 내부 링크: {N}개 확인, {M}개 수정
- 코드 블록 import: {N}개 확인, {M}개 수정

### 미해결 (해당 시)

| 문서 | 이슈 | 사유 |
|------|------|------|
| {경로} | {이슈 설명} | {3회 반복 후에도 미해결된 이유} |

### 변경 없음 (해당 시)

동기화가 필요한 불일치가 없습니다.
```

---

## 규칙

- **Code-first**: 문서의 모든 기술 내용은 실제 코드로 검증한다. 코드에 없는 내용을 문서에 추가하지 않는다.
- **CHANGELOG.md는 수정하지 않는다** — 자동 생성 대상.
- 패키지별 문서 동기화는 **병렬 서브에이전트**로 실행한다.
- 문서 스타일은 기존 문서의 톤과 구조를 따른다 — 새로운 형식을 도입하지 않는다.
- 코드와 이미 일치하는 문서는 건드리지 않는다.
- Mermaid 다이어그램 수정 시 `mermaid.md` 규칙을 준수한다.

$ARGUMENTS
