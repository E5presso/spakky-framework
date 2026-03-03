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
