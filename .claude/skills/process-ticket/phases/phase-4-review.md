# Phase 4: 구현 & 합리적 동료 리뷰 루프

> **Phase 진입 ping** (sub-agent 한정): (a) 구현 agent spawn 직전 1회 SendMessage(to: "team-lead", message: `phase: Phase 4 implement | issue: <N> | impl dispatched`); (b) 매 review iteration 진입 직후 1회 SendMessage(to: "team-lead", message: `phase: Phase 4 review iter <N> | issue: <N> | critical <count>`). SKILL.md "Phase 전환 progress ping" SSOT.

**역할 정의**:

| 역할 | 담당 | 책무 |
|------|------|------|
| 구현 에이전트 | Phase 4-1의 서브에이전트 (`opus`) | 코드 작성 및 의문점에 대한 응답(수용/반박) |
| 리뷰 에이전트 | `/review-code` 서브에이전트 (`opus`) | **합리적 동료 태세**로 의문점 생성 + 구현 에이전트 응답 재검증 |

두 에이전트는 **합리적 동료(reasonable peer)** 관계다. 리뷰 에이전트는 구현 에이전트가 합리적 판단을 내렸다는 **선의를 가정**하고, "이 구간이 실제로 문제를 일으키는가?"를 기본 질문으로 삼는다. 구체적 탐지 시그널이 매치되지 않으면 의문을 생성하지 않으며, 개방형 "왜 이 방식인가?" 질문은 금지된다. 이 루프의 목표는 **새 iteration에서 Critical이 0개 생성**될 때 PR을 생성하는 것이다 (Warning은 실제 운영 해 가능성이 구체적으로 관찰될 때만 보고하며, Info 심각도는 제거되었다). 즉 PR이 사람 앞에 놓였을 때 사람이 더 이상 본질적 질문을 하지 않는 상태를 로컬에서 보장한다.

> **리뷰 fan-out**: `/review-code`의 카테고리 SSOT는 `.claude/rules/review-heuristics.md` 14개 카테고리.

> **종료 조건 및 모순 에스컬레이션**: Critical만 신규 생성을 차단하고, Warning은 즉시 수정·반박·**후속 이슈 위임** 중 택일 (기술 부채로 전환 허용). Info 심각도는 리뷰어가 생성하지 않는다. 또한 새 iteration이 **직전 iteration에서 해소된 결정을 뒤집는 의문점**을 내면 자동 루프 중단 후 사용자에게 확정 방향 요청 — sub-agent로 실행 중이면 SKILL.md "사용자 질의 위임" 절의 `ask-delegate`로 메인에 위임 (`phase: Phase 4-2`, `trigger: review-loop-flip`), 사용자 직접 호출이면 `AskUserQuestion` 직접. 상세는 `/review-code` 스킬 참조.

## 4-1. 구현

- 서브에이전트 워크플로(CLAUDE.md 참조)에 따라 구현한다.
- 한 번에 하나의 작업 단위씩 진행한다.
- 모든 변경 코드의 테스트 커버리지 100% 충족 (메모리 `feedback_coverage_100.md`).

## 4-2. 합리적 동료 리뷰 루프

구현 완료 후 아래 사이클을 **새 iteration에서 Critical이 0개 생성될 때까지** 반복한다 (Warning은 반박 또는 후속 이슈 위임 허용). 이 루프는 `/process-ticket`이 주재하는 셸이며, 의문점 해소 프로토콜·수렴 조건·모순 에스컬레이션 규칙은 `/review-code` 스킬이 정의한다.

`/check` (format + lint + type + test + 레이어 의존)는 **리뷰 루프에 포함시키지 않고**, 수렴 직후 Phase 5(커밋) 진입 직전에 1회만 실행한다. 이유: 매 iteration마다 type/test를 돌리면 느리며, 리뷰 루프의 본질(합리적 의문점 수렴)과 무관한 기계적 회귀 검출이다. 타입/테스트 회귀는 최종 게이트에서 한 번에 걸러내도 충분하다.

**한 iteration의 흐름**:

1. **4-2a `/review-code`** — 서브에이전트에서 합리적 동료 리뷰 실행
   - 서브에이전트에게 **이슈 맥락**(목표, 수용 기준, 제약 사항)을 함께 전달한다.
   - 리뷰 에이전트는 의문점 리스트를 반환한다: `Critical` / `Warning` 분류. Info 섹션은 생성하지 않는다.
2. **4-2b 구현 에이전트 응답** — 각 의문점에 대해 **수용(코드 수정)** / **반박(근거 제시)** / **후속 이슈 위임**(Warning 한정) 중 택일
   - 수용: 코드를 수정하고 어떤 의문이 어떻게 해소됐는지 한 줄 요약을 남긴다.
   - 반박: 근거를 작성한다. 반박 근거는 아래 4가지 중 하나 이상을 충족해야 한다:
     1. **규칙 인용** — `.claude/rules/<file>.md`의 구체적 규칙을 인용하고 해당 규칙이 현 상황에 적용됨을 논증
     2. **코드베이스 선례** — 같은 패턴이 코드베이스에 이미 있음을 증명 (파일:라인 인용)
     3. **스코프 근거** — 현 이슈 스코프를 벗어남을 증명하고, 후속 이슈 생성(`/plan-issues` 호출)을 약속
     4. **도메인 근거** — 도메인 사전/ADR/스펙 문서에서 해당 판단의 근거를 인용
   - 후속 이슈 위임 (Warning 한정): `/plan-issues`로 이슈를 생성하여 스코프 밖 기술 부채로 전환. Critical은 즉시 해소가 원칙이므로 이 경로 금지.
   - 수정도 반박도 위임도 할 수 없는 Critical은 **미해소** 상태로 다음 iteration에 이월한다.
3. **4-2c 리뷰 에이전트 재검증** — 구현 에이전트의 응답을 평가
   - 수용 응답: 수정된 코드가 실제로 의문을 해소했는지 diff 재검증. 새 의문이 생겼으면 다음 iteration의 의문점 리스트에 편입.
   - 반박 응답: 위 4가지 근거 중 하나 이상을 충족하면 **인정(해소)**, 그렇지 않으면 **기각(미해소)**. 단순 "그렇게 했다" / "필요 없어 보인다"는 설득력 없음으로 기각된다.
   - 후속 이슈 위임 응답: 생성된 이슈 번호가 있으면 **인정(폐기)**. 이슈가 없으면 **기각**.

**Iteration 로그 포맷** (각 iteration마다 출력):

```
[Iter N/2] Review → Critical: X, Warning: Y (총 T개 의문)
[Iter N/2] Respond → 수용 A, 반박 B, 이슈 위임 D
[Iter N/2] Re-review → 수용 유효 A, 반박 인정 C (해소), 반박 기각 B-C (미해소), 위임 인정 D
[Iter N/2] 결과: Critical 미해소 X' → 다음 iteration / 수렴
```

**종료 조건** (Phase 5 진입 직전 최종 게이트):
1. **리뷰 루프 수렴**: 재디스패치된 리뷰 서브에이전트가 **Critical을 0개 생성**. Warning은 무시.
2. **최종 `/check`**: 수렴 직후 1회 실행. format + lint + type + test + 레이어 의존 모두 통과해야 Phase 5 진입.

리뷰 루프 수렴에 실패하면 4-2a로 복귀 (새 의문점이 추가됐을 수 있으므로 리뷰부터 재시작). 최종 `/check` 실패 시 타입/테스트를 수정한 후 Phase 5에 재진입한다 (리뷰 루프를 다시 돌지 않는다 — 기계적 회귀 수정은 검증 범위 안).

## 4-3. Max iteration 세이프가드

**기본 max: 2 iteration**. 합리적 동료 스탠스에서는 장시간 반복이 비용 낭비로 전환되는 경계가 낮다. Iter 1에서 초기 리뷰 + 구현 응답, Iter 2에서 재검증으로 수렴을 판정한다.

초과 시 동작은 모드에 따라 분기한다:

- **Default 모드**: 사용자 escalation. 남은 미해소 의문점과 직전 반박 기각 내용을 동봉하여 "(1) 수동 수정 후 재개 / (2) 반박 근거 추가 후 재검증 / (3) 현 상태로 PR 생성 / (4) 작업 중단" 중 선택받는다 — sub-agent로 실행 중이면 SKILL.md "사용자 질의 위임" 절의 `ask-delegate`로 메인에 위임 (`phase: Phase 4-3`, `trigger: max-iteration-exceeded`), 사용자 직접 호출이면 `AskUserQuestion` 직접.
- **`--overnight` 모드**: 사용자 escalation 없이 남은 미해소 의문점을 **PR body의 "HUMAN REVIEW NEEDED" 섹션**으로 기록하고 Phase 5 진입. 각 항목은 "[카테고리] 의문 내용 | 직전 반박 근거 | 기각 사유" 포맷.

> **반박 기각 = 미해소.** 다른 반박 근거 시도 또는 수용 전환만 유효. 동일 반박 반복은 해소 불가.
> **Iter 2에서 동일 Critical 재제기** → "해소 실패"로 간주하여 escalation 경로(Default: 사용자 / `--overnight`: PR body 기록)로 전환.
