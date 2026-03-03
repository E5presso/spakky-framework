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
