---
name: harness-update
description: Harness update workflow. Auto-loads when agent modifies instructions, skills, prompts, or hooks files.
---

# 하네스 변경 스킬

## 핵심 원칙

| 원칙                         | 요약                                                                        |
| ---------------------------- | --------------------------------------------------------------------------- |
| **환경을 설계하라**          | 에이전트 실패 → "능력 부족"이 아니라 "환경에 무엇이 빠졌는가?" 질문         |
| **지도를 줘라, 매뉴얼 말고** | 거대 단일 문서는 실패. 분산된 cross-linked docs, repo-local 아티팩트로 구성 |
| **단순화 = 성능 향상**       | 도구/규칙 제거할수록 에이전트가 빨라지고 안정됨                             |
| **Bitter Lesson**            | 모델 업그레이드 시 불필요해진 harness 규칙 제거                             |
| **제약이 신뢰를 만든다**     | 솔루션 공간 확장이 아니라 제약으로 품질 확보                                |
| **토큰 = 비용**              | 모든 규칙은 토큰 비용 정당화 필요. 중복·저신호 규칙 제거 우선                |

## 컨텍스트 패턴

| 패턴                 | 적용                                                   |
| -------------------- | ------------------------------------------------------ |
| **KV-cache 안정화**  | 프롬프트 prefix 고정, 도구는 masking으로 제어          |
| **파일 = 메모리**    | 컨텍스트에 모든 것 담지 말고, 파일에 쓰고 필요 시 로드 |
| **목표 반복 주입**   | 긴 태스크에서 todo.md로 목표 망각 방지                 |
| **에러 보존**        | 실패 로그 지우지 말고 축적 → 모델 학습 자원            |
| **Context Rot 대비** | 최소 고신호 토큰만 로드, 나머지는 on-demand            |
| **Goldilocks Zone**  | 너무 구체적(깨지기 쉬움) ↔ 너무 추상적(추측 유발) 사이 |

## 하네스 3영역

1. **Context engineering**: 코드베이스 지식 + 동적 컨텍스트
2. **Architectural constraints**: 린터, 테스트 등 결정론적 강제
3. **Garbage collection**: 문서 불일치·위반 정리 자동화

---

## 하네스 구조

| 파일                             | 역할               | 적용                    |
| -------------------------------- | ------------------ | ----------------------- |
| `agents/*.agent.md`              | 에이전트 행동 규칙 | 에이전트 활성화 시      |
| `hooks/hooks.json`               | 세션 수명주기 훅   | 코딩 에이전트 이벤트 시 |
| `skills/<name>/SKILL.md`         | 재사용 스킬        | 관련 작업 감지 시       |
| `instructions/*.instructions.md` | 파일 패턴별 규칙   | 해당 파일 작업 시       |
| `prompts/*.prompt.md`            | VS Code 워크플로우 | 프롬프트 호출 시        |
| `copilot-instructions.md`        | 전역 지침          | 항상                    |

> **Skill vs Prompt**: 동일 워크플로우는 Skill 하나만. Prompt는 VS Code 고유 기능(`agent:`, `tools:`, `${input:}`) 필요 시에만.

### 인스트럭션 맵

| 파일                    | 패턴                 |
| ----------------------- | -------------------- |
| `behavioral-guidelines` | `**/*`               |
| `tool-usage`            | `**/*`               |
| `api-reference`         | `**/*.py`            |
| `python-code`           | `**/*.py`            |
| `mermaid`               | `**/*.md`            |
| `test-writing`          | `**/tests/**/*.py`   |
| `domain`                | `**/domain/**/*.py`  |
| `aspect`                | `**/aspects/**/*.py` |
| `plugin`                | `plugins/**/*.py`    |
| `monorepo`              | `**/pyproject.toml`  |

---

## 변경 원칙

1. **최소 범위**: 세션 자동화 → `hooks/` | 재사용 → `skills/` | 파일 패턴 → `instructions/` | VS Code 전용 → `prompts/`
2. **중복 금지**: 한 곳에만 기록
3. **쓰기 보호**: 하네스 변경 전 사용자 승인 필요

## 워크플로우

1. **위치 결정**: 규칙 적용 상황 분석 → 적합한 파일 선택
2. **제안**: 전체 변경 내용 마크다운 출력 → 승인 대기
3. **적용**: 승인 후 파일 수정 → 정합성 확인
