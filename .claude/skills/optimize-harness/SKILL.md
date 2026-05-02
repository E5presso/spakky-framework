---
name: optimize-harness
description: 하네스 전체 규칙을 5-test 게이트로 순회하여 토큰 제거 + 기능 동등성 보장. 최적화 후 evaluate-harness로 회귀 검증.
argument-hint: "[scope: rules|skills|all]"
user-invocable: true
---

# Optimize Harness — 5-Test 기반 하네스 최적화

`harness-writing.md`의 **5-Test 게이트**를 모든 규칙에 일괄 적용하여 토큰 제거 + 기능 동등성을 보장한다. 최적화 후 `/evaluate-harness`를 자동 호출하여 회귀 검증.

## 사용법

```bash
/optimize-harness            # 전체
/optimize-harness rules      # rules/*.md만
/optimize-harness skills     # skills/*/SKILL.md만
```

---

## Phase 1: 토큰 측정 (사전)

스코프 내 모든 파일의 토큰 수를 집계 (대략 `wc -w * 1.3`):

```
rules/charter.md         412 tokens
rules/python-code.md     891 tokens
...
total                  4,231 tokens
```

이 수치를 Phase 7 회귀 검증의 **before** 기준으로 기록.

## Phase 2: 5-Test 일괄 적용 (병렬 서브에이전트)

각 파일을 **별도 서브에이전트**(general-purpose)로 분배. 각 서브에이전트는 담당 파일의 모든 규칙을 5-Test로 순회:

### 5-Test 게이트

| Test | 질문 | 실패 처리 |
|------|------|----------|
| 1. 삭제 | 이 규칙을 삭제하면 무슨 일이 벌어지는가? | "아무 일도 없음" → 삭제 후보 |
| 2. 비추론 | 코드·상위 규칙에서 추론 가능한가? | 추론 가능 → 삭제 후보 |
| 3. 중복 | 다른 규칙과 동일/유사 차단력? | 중복 → 통합 후보 |
| 4. 행동 변화 | 있을 때와 없을 때 에이전트 행동이 다른가? | 동일 → 삭제 후보 |
| 5. 보편성 | 단 1건의 사례에만 적용되는가? | 1건 한정 → 추상화 또는 삭제 후보 |

각 서브에이전트는 **수정 제안만** 작성하고 실제 파일은 수정하지 않는다 (메인이 통합).

## Phase 3: 제안 통합 & 충돌 해소

메인이 서브에이전트들의 제안을 통합:

- 동일 규칙에 대한 상충 제안 → 보수적 쪽 채택 (유지 > 통합 > 삭제)
- 통합 제안은 위치(어느 파일로) 결정
- 5-Test 메모를 별첨하여 제안 근거 보존

## Phase 4: 사용자 승인 게이트

통합 제안을 사용자에게 보고:

```
## Optimize Harness 제안

### 삭제 후보 (5건)
- rules/X.md §3 "Y 규칙": 5-Test 1,4 fail — 삭제력 0, 행동 동일

### 통합 후보 (3건)
- rules/A.md §2 + rules/B.md §5 → rules/A.md §2 (중복)

### 추상화 후보 (2건)
- ...

승인 → 적용
거절 → 취소
부분 승인 → 항목별 선택
```

`AskUserQuestion`으로 객관식 제시. 승인 없이 진행 금지.

## Phase 5: 적용

승인된 제안만 메인이 직접 적용 (Edit 도구). 서브에이전트는 수정 권한 없음.

## Phase 6: 토큰 측정 (사후) & 차이

```
before: 4,231 tokens
after:  3,108 tokens
saved:  1,123 tokens (26.5%)
```

## Phase 7: 회귀 검증 — `/evaluate-harness` 자동 호출 (필수)

최적화로 차단력이 손실되지 않았는지 외부 검증:

```
/evaluate-harness {scope}
```

결과 분기:

- **Critical 1개 이상**: 적용한 변경 중 차단력 손실 발생. 사용자에게 즉시 보고하고 **롤백 후보 제시** (어느 변경이 회귀를 일으켰는지 추정).
- **Warning만**: 보고 후 사용자 판단 대기.
- **모두 통과**: 최적화 완료 보고.

**Phase 7을 건너뛰지 않는다.** 최적화 후 회귀 검증은 선택이 아니라 필수.

---

## 규칙

- 5-Test 적용은 **외부 서브에이전트**가 수행한다 (메인이 직접 평가 금지, 자기확증 편향 차단).
- 사용자 승인 없이 파일 수정 금지. Phase 4 게이트는 의무.
- Phase 7 회귀 검증을 통과하지 못한 변경은 즉시 롤백 후보. 사용자에게 보고.
- 한 번에 너무 많은 변경(예: 50% 이상 토큰 감소)을 적용하지 않는다. 분할 적용 권장.

$ARGUMENTS
