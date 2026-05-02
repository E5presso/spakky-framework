# Phase 3.5: 후속 티켓 회수 라운드 (fallback fixed-point)

**SSOT**: `behavioral-guidelines.md` "스펙 검증 / 후속 티켓" 절은 후속 티켓 default = 즉시 분해. 본 phase는 1차 메커니즘이 아니라 **즉시 spawn이 누락된 번호만 흡수하는 fallback 게이트**다 (Phase 3 §3-3-quinque "후속 티켓 즉시 spawn" SSOT 정합).

## 절차

1. wave 전체에서 sub-agent가 보고한 `spawned` 번호들의 합집합 `F`를 계산한다.
2. 메인 세션이 §3-3-quinque에서 즉시 spawn한 `spawned_dispatched` 집합 `D`를 계산한다.
3. **누락 집합 `M := F - D - {이미 closed인 번호}`**.
4. **`M`이 비어 있으면 즉시 Phase 4로 진행** — 정상 경로. 본 phase는 §3-3-quinque가 모든 spawn을 흡수했음을 검증하는 idempotent 게이트로만 동작한다.
5. **`M`이 비어 있지 않으면**, 누락된 즉시 spawn을 회수한다:
   - 사용자에게 1줄 알림: `[autopilot] Phase 3.5 fallback: 즉시 spawn 누락 {len(M)}개 회수 ({M})`.
   - `M`을 새 입력으로 받아 **autopilot 자체를 재귀 진입**한다 (Phase 1부터 재시작). 의존 관계는 GitHub 본문의 `Blocked by:` / task list / `blockedBy` 표기에서 다시 읽어 DAG를 재구성한다.
6. 재귀 호출이 반환하면 그 라운드에서 또 새로운 `spawned`가 발생할 수 있으므로, 본 fallback 절차를 `M == ∅`이 될 때까지 반복(fixed-point)한다. 라운드 깊이에 자의적 상한은 두지 않는다 — 본 스킬의 궁극 목표가 "쏟아지는 후속 티켓 모두 흡수"이기 때문.
7. **순환 분해 감지**: 라운드 `r`의 `M`이 라운드 `r-1`의 `M`과 동일하거나 부분집합 관계가 역전(이전 라운드에서 본 번호가 다시 등장)하면 circular spawning으로 판정하고 stop & 사용자 질의 (charter §4-A 질의 트리거 — 분해가 수렴하지 않는 기술적 모순). 임의 깊이 제한이 아닌 논리적 모순 검출.

## 정상 경로 동작

§3-3-quinque이 모든 wave에서 즉시 spawn을 수행하면 `M = ∅`이 되어 본 phase는 검증만 하고 즉시 통과한다. 누락이 누적되어 본 phase가 실제 spawn을 수행해야 하는 경우는 §3-3-quinque의 결함(메인 세션 종료·메시지 라우팅 실패 등)이 의심되므로, 누락 1건 이상 시 §3.6-2 메타 fix 티켓 후보로도 함께 등록한다 ("왜 즉시 spawn이 누락되었는가" 추적).
