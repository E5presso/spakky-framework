# Project Agent Harness

Codex 표준 에이전트 하네스의 SSOT는 이 파일과 `.agents/rules/`, `.agents/skills/`입니다. Claude Code는 `CLAUDE.md`와 `.claude/` 래퍼로 같은 정본을 참조합니다.

## Project Overview

> TODO: 프로젝트 이름, 런타임, 패키지 구조, 주요 진입점을 실제 코드 기준으로 작성한다.

## Project Quick Reference

| 경로 | 역할 |
|------|------|
| `TODO` | TODO |

## Core Workflows

- 코드 변경 전 관련 파일과 문서를 실제로 확인한다.
- 코드 변경 후 관련 문서를 동기화한다.
- 하네스 변경 후 포인터와 래퍼 참조가 깨지지 않았는지 검증한다.

## Documentation Maintenance Rules

- **Code-first**: 모든 기술은 실제 코드 기반이다. 추측으로 문서화하지 않는다.
- **Cross-reference**: 문서화 전 정확한 코드 라인, 파일 경로, import 경로를 확인한다.
- **Priority**: Code > project docs > this file > README. 불일치 시 낮은 우선순위 문서를 수정한다.

## Rules

| 영역 | 정본 |
|------|------|
| 에이전트 헌장 | `.agents/rules/charter.md` |
| 행동 원칙 | `.agents/rules/behavioral-guidelines.md` |
| 문서화 | `.agents/rules/documentation.md` |
| 리뷰 휴리스틱 | `.agents/rules/review-heuristics.md` |
| 하네스 작성 | `.agents/rules/harness-writing.md` |
| 스킬 작성 | `.agents/rules/write-skill.md` |

## Project-Specific Conventions

> TODO: rules 파일에 없는 프로젝트 고유 예외만 기록한다.
