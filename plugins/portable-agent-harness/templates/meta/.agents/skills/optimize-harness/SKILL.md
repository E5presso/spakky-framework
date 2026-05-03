---
name: optimize-harness
description: 하네스 규칙과 스킬을 5-Test 게이트로 점검해 중복과 토큰 낭비를 줄입니다.
argument-hint: "[scope: rules|skills|all]"
user-invocable: true
---

# Optimize Harness

하네스 파일을 5-Test 게이트로 점검해 차단력은 유지하고 중복과 stale 문구를 줄인다. 사용자 승인 없이 파일을 수정하지 않는다.

## 사용법

```bash
/optimize-harness
/optimize-harness rules
/optimize-harness skills
```

## 5-Test 게이트

각 규칙과 스킬 지시문에 다음 질문을 적용한다:

1. 삭제하면 구체적 위반이 재발하는가.
2. 코드, 문서, 상위 규칙에서 이미 추론 가능한가.
3. 같은 차단력을 가진 규칙이 이미 있는가.
4. 이 문장이 있을 때 에이전트 행동이 실제로 달라지는가.
5. 단일 사건 기록이 아니라 여러 상황에 적용되는 보편 원리인가.

## Phase 1: 측정

- 대상 파일 목록을 만든다.
- 대략적인 길이(`wc -w`)와 중복 후보를 기록한다.

## Phase 2: 제안

삭제, 통합, 추상화 후보를 제안한다. 가능하면 read-only 서브에이전트 또는 독립 검토자를 사용한다.

## Phase 3: 승인

변경 전 사용자에게 다음을 보고한다:

- 삭제 후보
- 통합 후보
- stale 문구 후보
- 예상 위험

승인된 항목만 적용한다.

## Phase 4: 회귀 검증

적용 후 `/evaluate-harness` 또는 동등한 포인터 검증을 실행한다. broken pointer가 생기면 즉시 보고하고 수정 또는 롤백 후보를 제시한다.

$ARGUMENTS
