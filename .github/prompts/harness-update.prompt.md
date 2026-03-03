---
name: harness-update
description: 로컬 하네스 변경 워크플로우
agent: spakky-dev
tools:
  - read/readFile
  - search
  - edit/editFiles
  - todo
---

# 하네스 변경 프로토콜

로컬 프로젝트 하네스 변경 시 이 워크플로우를 따릅니다.

## 하네스 구조

| 파일 | 역할 | 적용 시점 |
|------|------|----------|
| `.github/agents/spakky-dev.agent.md` | 에이전트 행동 규칙 | 에이전트 활성화 시 |
| `.github/hooks/hooks.json` | 세션 수명주기 훅 (shell 명령) | 코딩 에이전트 이벤트 발생 시 자동 |
| `.github/skills/<name>/SKILL.md` | 재사용 가능한 에이전트 스킬 | 에이전트가 관련 작업 감지 시 로드 |
| `.github/instructions/*.instructions.md` | 파일 패턴별 규칙 | 해당 파일 작업 시 자동 |
| `.github/prompts/*.prompt.md` | 워크플로우 정의 | 프롬프트 호출 시 |
| `.github/copilot-instructions.md` | 전역 AI 지침 | 항상 |

### 인스트럭션 목록

| 파일 | 적용 패턴 | 내용 |
|------|-----------|------|
| `api-reference.instructions.md` | `**/*.py` | Spakky API import 경로 |
| `python-code.instructions.md` | `**/*.py` | 타입 안전, 네이밍, 로깅 |
| `test-writing.instructions.md` | `**/tests/**/*.py` | 테스트 구조, TDD, 커버리지 |
| `error-classes.instructions.md` | `**/error.py` | 에러 클래스 계층 구조 |
| `domain.instructions.md` | `**/domain/**/*.py` | DDD 빌딩 블록 패턴 |
| `aspect.instructions.md` | `**/aspects/**/*.py` | AOP Aspect 구조 패턴 |
| `plugin.instructions.md` | `plugins/**/*.py` | 플러그인 개발 규칙 |
| `monorepo.instructions.md` | `**/pyproject.toml` | 모노레포 도구 실행 원칙 |

### 훅 목록 (`.github/hooks/`)

| 파일 | 이벤트 | 동작 |
|------|--------|------|
| `hooks.json` | `sessionStart` | `uv sync --all-packages --all-extras` — 세션 시작 시 전체 패키지 의존성 동기화 |

### 스킬 목록 (`.github/skills/`)

| 폴더 | 스킬 이름 | 용도 |
|------|----------|------|
| `coverage/` | `coverage` | 패키지 커버리지 측정 및 100% 달성 워크플로우 |
| `create-plugin/` | `create-plugin` | 새 플러그인 패키지 스캐폴딩 (9단계) |
| `review-pr/` | `review-pr` | PR 리뷰 댓글 분류 → 수정 → 검증 → 응답 |

### 프롬프트 목록

| 파일 | 용도 |
|------|------|
| `commit.prompt.md` | Conventional Commits 메시지 작성 |
| `implement.prompt.md` | 기능 구현 워크플로우 |
| `test.prompt.md` | 테스트 작성 워크플로우 |
| `coverage.prompt.md` | 커버리지 개선 워크플로우 |
| `plugin.prompt.md` | 플러그인 생성 워크플로우 |
| `pr.prompt.md` | PR 생성 워크플로우 |
| `review.prompt.md` | PR 리뷰 피드백 반영 워크플로우 |
| `harness-update.prompt.md` | 하네스 변경 워크플로우 |

## 변경 원칙

1. **최소 범위**: 가장 구체적인 위치에 규칙 추가
   - 코딩 에이전트 세션 자동화 → `hooks/`
   - 재사용 가능한 에이전트 스킬 → `skills/`
   - 특정 파일 패턴 → `instructions/`
   - 반복 워크플로우 → `prompts/`
   - 모든 작업 공통 → `agent.md`

2. **중복 금지**: 한 곳에만 기록, 다른 곳에서 참조

3. **쓰기 보호**: 하네스 파일 변경 전 사용자 승인 필요

## 워크플로우

### 1. 변경 위치 결정
- 새 규칙이 어떤 상황에 적용되는지 분석
- 가장 적합한 파일 선택

### 2. 변경 제안
- 전체 변경 내용을 마크다운으로 출력
- 사용자 명시적 승인 대기

### 3. 적용
- 승인 후 파일 수정
- 관련 문서 정합성 확인
