---
description: 로컬 자동 메모리를 감사하여 공유 하네스로 승격할 패턴을 식별. 의미 중복/커버리지 부족을 LLM으로 판정하고, 최종 반영은 /optimize-harness로 위임.
user-invocable: true
argument-hint: "[옵션: feedback|project|reference]"
---

# Promote Memory — 로컬 메모리 → 정식 하네스 승격

각 에이전트 인스턴스의 로컬 auto-memory에 체화된 행동 양식을 감사하여, 공유 하네스로 승격할 가치가 있는 패턴만 골라 `/optimize-harness`로 위임한다. 메모리 사일로를 막고 하네스의 일관된 UX를 유지하는 것이 목적.

## 대상 경로

- **메모리 루트**: `~/.codex/memories/`
  - 레포 루트는 `git rev-parse --show-toplevel`로 취득하고, `MEMORY.md`에서 해당 repo 경로에 매칭되는 항목만 후보로 삼는다.
  - `MEMORY.md`는 인덱스이므로 직접 승격 대상에서 제외하고, 연결된 `rollout_summaries/`·`skills/` 항목을 근거로 읽는다.
- **하네스 대상** (spakky-framework 전용):
  - `/.agents/rules/*.md`
  - `/AGENTS.md`
- **참조 전용** (중복 감지용, 수정 대상 아님):
  - 레포 루트 `AGENTS.md`
  - 글로벌 Codex 설정/메모리는 사용자별로 내용이 달라 판정이 비결정적이 되므로 **참조 대상에서 제외**한다.

## Phase 0 — 입력 수집

인자가 `feedback|project|reference` 중 하나면 해당 타입만 대상. 인자 없으면 전체. 그 외 입력은 거부하고 재입력 요청.

## Phase 1 — 인벤토리

1. 메모리 파일을 `Glob`으로 전체 수집 (`MEMORY.md` 제외). 각 파일을 `Read`하여 frontmatter(`name`/`description`/`type`) + body 보관.
2. Phase 0 필터가 있으면 `type`으로 선별.
3. 하네스 대상 파일 전체 `Read`. 참조 파일도 `Read`하되 수정 금지 플래그 유지.

## Phase 2 — 4분류 판정

각 메모리에 대해 하네스 전문과 대조하여 아래 중 하나로 분류. 판정은 메인 컨텍스트에서 직접 수행 (서브에이전트 불필요 — 입력 규모 작음).

| 분류 | 정의 | 후속 |
|------|------|------|
| `covered` | 하네스에 동일 취지 규칙이 이미 존재 | 행동 없음 |
| `refine` | 하네스에 관련 규칙은 있으나 메모리가 더 구체/정확한 표현 보유 | 해당 rules 파일 보강 제안 |
| `promote` | 하네스 미커버 + 일반화 가능한 행동 양식 | 신규 항목 추가 제안 |
| `personal` | 특정 세션/태스크 맥락 한정, 일반화 부적합 | 행동 없음 |

산출물 테이블: `memory_file | verdict | target_rule_file | rationale (≤1문장) | proposed_change (≤3줄 요약)`.

판정 기준:
- 메모리 body의 "Why"가 코드베이스에서 자체 추론 가능하면 `personal` (하네스 비추론 테스트와 동일 기준).
- 하네스 규칙의 상위어/하위어 관계도 중복으로 간주하여 `covered` 또는 `refine`으로 분류.
- **원천 스코프 필터**: 메모리의 evidence가 spakky-framework 작업에서 발생한 것이 아니면 (예: 글로벌 PR 작성 규칙, GitHub Issue 생성 규칙 등) `personal`로 분류하여 KR (spakky-framework) 하네스 확장을 방지한다. 증거가 모호하면 `personal`을 기본값으로 한다.

## Phase 3 — 승격 후보 선별

1. `covered`/`personal` 건수만 사용자에게 집계 보고 (상세 나열 생략).
2. `refine`/`promote`가 0건이면 "승격 대상 없음" 보고 후 종료.
3. `refine`/`promote` 후보를 `사용자 질의` multiSelect로 제시. UI 제약상 옵션은 최대 4개. 후보가 5건 이상이면 **배치를 나누어 사용자 질의를 여러 번 호출**한다 — "Other (직접 입력)"로 초과분을 우회하지 않는다 (구조화된 verdict/target 데이터 유실 방지).

## Phase 4 — `/optimize-harness` 위임

선택된 후보마다:

1. `harness-writing.md` "5가지 테스트" SSOT (Single Source of Truth)를 **먼저 스스로 통과**시키고, 추가로 **3회 실패 확인**: 해당 취지를 뒷받침하는 증거가 3건 이상 존재하는가 (동일/유사 취지의 메모리 복수, 또는 이번 세션 내 명시적 반복 피드백). 단일 메모리만으로는 통과 불가 — 미충족 시 해당 후보를 보류한다.
2. 통과하면 대상 rules 파일에 Edit 적용. 실패하면 해당 후보를 보류 목록으로 이동하고 사유 기록.
3. 편집 원칙: 명령형 문체, 예시 우선, AGENTS.md는 ≤50줄 유지, 파일당 ≤900 tokens.
4. **로컬 메모리 파일은 수정하지 않는다** — 정리는 사용자의 `/remember` 수동 조작에 일임.
5. **수정 후 의무 작업** (`/optimize-harness`의 "수정 후" 섹션 준수):
   - `/evaluate-harness`를 **실행**한다 — 단순 제안이 아님.

## Phase 5 — 결과 보고

Phase 4에서 실행한 `/evaluate-harness` 결과를 포함하여 보고한다.

```
## 승격 결과

- 분석: {total}건 (covered: N, refine: N, promote: N, personal: N)
- 반영: {count}건
  - {rules_file}: {한 줄 요약}
- 보류: {count}건 (사유 포함)
- `/evaluate-harness` 결과: {pass/fail 요약}

## 후속 제안

- 필요 시 `/remember`로 개별 메모리 정리
```

## 규칙

- **메모리 파일·참조 파일은 수정 금지.**
- **하네스 Edit은 `/optimize-harness` 체크리스트 통과 건에 한해서만** 수행한다.
- 사용자 승인(Phase 3) 없이 Phase 4로 진행하지 않는다.
- Phase 2 판정 결과는 반드시 사용자에게 테이블로 노출한다 — 블랙박스 판정 금지.
- `사용자 질의` 선택지는 최대 4개 (UI 제약). 초과하는 후보는 재호출로 분할 처리.
- 본 스킬은 shell 스크립트를 포함하지 않는다. 모든 I/O는 Read/Glob/Edit 도구로만 수행.
