---
name: evaluate-harness
description: 하네스 규칙과 스킬의 포인터, 중복, 실행 가능성, stale 사실을 독립적으로 점검합니다.
argument-hint: "[scope: rules|skills|all]"
user-invocable: true
---

# Evaluate Harness

하네스가 선언한 규칙과 스킬이 실제 프로젝트에서 유효한지 점검한다. 이 스킬은 평가와 보고가 본분이며, 사용자 승인 없이 하네스 파일을 수정하지 않는다.

## 사용법

```bash
/evaluate-harness
/evaluate-harness rules
/evaluate-harness skills
```

## Phase 1: 대상 수집

- `rules`: `AGENTS.md`, `.agents/rules/*.md`, `.codex/AGENTS.md`, `CLAUDE.md`, `.claude/rules/*.md`
- `skills`: `.agents/skills/*/SKILL.md`, `.claude/skills/*/SKILL.md`
- `all`: 위 전체

## Phase 2: 검증

다음 항목을 확인한다:

- 정본 파일이 존재하는가.
- 래퍼의 `@...` 참조가 실제 파일로 resolve되는가.
- `.agents`와 `.claude`의 rule/skill set이 의도대로 일치하는가.
- 스킬 본문이 존재하지 않는 명령, 파일, 도구 이름을 참조하지 않는가.
- rules가 프로젝트 구조와 맞지 않는 stale 사실을 포함하지 않는가.
- 같은 차단력을 가진 규칙이 중복되어 있지 않은가.

가능하면 read-only 서브에이전트 또는 독립 검토자를 사용해 자기확증 편향을 줄인다.

## Phase 3: 보고

보고서는 다음 형식으로 작성한다:

```markdown
## Evaluate Harness 보고서

스코프: {scope}
평가 대상: {count}

### Critical
- {정본 또는 래퍼가 깨져 로딩 실패가 예상되는 문제}

### Warning
- {stale 사실, 중복, 부분 불일치}

### 통과
- {검증된 항목 요약}
```

## 규칙

- 평가 중 발견한 문제를 즉시 수정하지 않는다. 수정이 필요하면 별도 변경으로 제안한다.
- broken pointer는 critical로 분류한다.
- 프로젝트 전용 정책 판단이 필요한 항목은 사용자에게 확인한다.

$ARGUMENTS
