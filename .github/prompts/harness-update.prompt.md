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

## 하네스 구조

| 파일 | 역할 | 적용 시점 |
|------|------|----------|
| `.github/agents/spakky-dev.agent.md` | 에이전트 행동 규칙 | 에이전트 활성화 시 |
| `.github/hooks/hooks.json` | 세션 수명주기 훅 | 코딩 에이전트 이벤트 시 자동 |
| `.github/skills/<name>/SKILL.md` | 재사용 가능한 에이전트 스킬 | 에이전트가 관련 작업 감지 시 |
| `.github/instructions/*.instructions.md` | 파일 패턴별 규칙 | 해당 파일 작업 시 자동 |
| `.github/prompts/*.prompt.md` | VS Code 워크플로우 | 프롬프트 호출 시 |
| `.github/copilot-instructions.md` | 전역 AI 지침 | 항상 |

> **Skill vs Prompt**: 동일 워크플로우는 Skill 하나만 유지. Prompt는 VS Code 고유 기능(`agent:`, `tools:`, `${input:}`)이 필요한 경우에만 추가.

### 인스트럭션

| 파일 | 패턴 | 내용 |
|------|------|------|
| `api-reference` | `**/*.py` | Spakky API import 경로 |
| `python-code` | `**/*.py` | 타입 안전, 네이밍, 로깅 |
| `test-writing` | `**/tests/**/*.py` | 테스트 구조, TDD |
| `error-classes` | `**/error.py` | 에러 클래스 계층 구조 |
| `domain` | `**/domain/**/*.py` | DDD 빌딩 블록 |
| `aspect` | `**/aspects/**/*.py` | AOP Aspect 패턴 |
| `plugin` | `plugins/**/*.py` | 플러그인 개발 규칙 |
| `monorepo` | `**/pyproject.toml` | 모노레포 도구 실행 원칙 |

### 훅

| 이벤트 | 동작 |
|--------|------|
| `sessionStart` | `uv sync --all-packages` 자동 실행 |
| `sessionEnd` | `harness-review.py` 실행 → 토큰/중복/변경 파일 분석 |

### 스킬

| 폴더 | 용도 |
|------|------|
| `harness-review/` | 세션 후 메타 리뷰 (정량+정성 평가) |
| `improve-coverage/` | 커버리지 측정 → 100% 달성 |
| `create-plugin/` | 플러그인 스캐폴딩 (9단계) |
| `review-pr/` | PR 리뷰 댓글 처리 |

### 프롬프트

| 파일 | 용도 |
|------|------|
| `commit.prompt.md` | Conventional Commits 메시지 작성 |
| `implement.prompt.md` | 기능 구현 워크플로우 |
| `test.prompt.md` | 테스트 작성 워크플로우 |
| `pr.prompt.md` | PR 생성 워크플로우 |
| `harness-update.prompt.md` | 하네스 변경 워크플로우 |

## 변경 원칙

1. **최소 범위**: 세션 자동화 → `hooks/` | 재사용 스킬 → `skills/` | 파일 패턴 → `instructions/` | VS Code 전용 → `prompts/` | 전역 → `agent.md`
2. **중복 금지**: 한 곳에만 기록. 동일 워크플로우에 prompt+skill 양쪽 만들지 말 것.
3. **쓰기 보호**: 하네스 파일 변경 전 사용자 승인 필요

## 워크플로우

1. **위치 결정**: 새 규칙이 어떤 상황에 적용되는지 분석 → 가장 적합한 파일 선택
2. **제안**: 전체 변경 내용을 마크다운으로 출력 → 사용자 승인 대기
3. **적용**: 승인 후 파일 수정 → 관련 문서 정합성 확인

