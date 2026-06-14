# Phase 6: CI & 리뷰 모니터링

> **Phase 진입 ping (sub-agent 한정) — 동작 시작 어휘만 허용.** watch.sh 첫 호출과 **같은 메시지의 두 tool_use** 안에서 SendMessage 1줄을 묶어 송신한다. 정형: `phase: Phase 6 monitor | issue: <id> | watch.sh started, polling pr=#<N>`. **금지 어휘 (turn-boundary 안티패턴)**: `monitor armed` / `watch.sh entering` / `watch.sh preparing` / `monitor ready` / `about to poll` — 동작이 아직 시작되지 않은 어휘는 sub-agent가 ping 송신을 turn 종료 시그널로 오해하는 회귀 진입점이며, 본 절이 명시적으로 차단한다. 정상 ping은 watch.sh가 이미 같은 turn 안에서 호출되었음을 어휘로 박는다 (`started`, `polling`). **ping 송신은 단방향 + 같은 turn 안에서 즉시 watch.sh 포그라운드 호출 — ping과 watch.sh Bash 호출이 같은 메시지의 두 tool_use로 묶이지 않으면 turn 종료 안티패턴**.

> **절대 명령·안티패턴 4종·외부 백그라운드 경로 금지·DONE 즉시 정지: `monitor-pr/SKILL.md` §"절대 명령" SSOT.**
> Phase 6 진입 시 해당 SKILL.md를 Read 후 그대로 적용한다.
>
> **DONE 즉시 정지 + auto-merge continuation.** DONE 관찰 후 추가 watch/poll/재검증 호출 금지. `DONE reason=mergeable-clean`은 Phase 6만의 terminal이므로 `--auto-merge` 또는 autopilot 하위 실행에서는 `phase7_ready` 기록 직후 같은 turn 안에서 Phase 7 ping → Phase 8 squash merge + cleanup까지 계속한다. `phase7_ready`만 기록하고 `status: blocked|awaiting-merge|merge approval required`로 반환하면 형식 위반이다.

> **자가검사 (turn 종료 직전 의무).** Phase 6 안에서 turn 종료 candidate 직전에 다음 3개 질문에 모두 Yes로 답할 수 있어야 한다 — 하나라도 No면 turn 종료 금지, 즉시 watch.sh 재호출로 복귀. **단 마지막 `watch.sh` 출력이 `EVENT reason=interrupt`이면 본 자가검사를 면제한다** — interrupt turn 종료는 메인 지시 수신을 위한 yield이며 재기동이 구조적으로 보장된다 (`monitor-pr/SKILL.md` §"Interrupt — 능동 지시 yield"):
>
> 1. **이번 turn에서 `watch.sh`를 적어도 1회 포그라운드 Bash로 호출했는가?** (호출 없이 ping만 보낸 turn은 종료 금지 — §3-3-bis 모순 C(monitor-entry-idle) 트리거).
> 2. **마지막 watch.sh 호출의 stdout에 `DONE reason=...` 줄이 emit되었는가?** (EVENT만 관찰됐고 DONE이 없으면 같은 turn 안에서 case 분기 실행 후 watch.sh 재호출).
> 3. **DONE reason이 `{merged, mergeable-clean, closed-without-merge, awaiting-human-review}` 중 하나로 분기 처리되었는가?** (분기 없는 종료는 EVENT consumer 부재 안티패턴).

## 실행 루프 (서브에이전트 본인이 같은 turn 안에서 수행)

**Phase 6 진입 직후 1회**: 워크트리 루트에 stale `.monitor-interrupt`가 있으면 삭제한다 (`rm -f {워크트리 경로}/.monitor-interrupt`) — 이전 phase에서 메인 세션이 보낸 지시의 sentinel이 첫 `watch.sh` cycle에서 spurious `reason=interrupt`(지시 없는 turn 종료 → 영구 idle)를 일으키는 것을 차단한다. 진입 시 1회만 수행하며 INIT 재진입마다 반복하지 않는다 — 모니터링 중 메인 세션이 쓴 sentinel을 지우면 능동 지시가 유실된다.

그 다음 너는 아래 4단계를 자기 turn 안에서 순서대로 수행한다. 각 단계 사이에 turn을 종료하지 않는다. DONE이 관찰될 때까지 1↔4 루프를 반복한다.

1. **INIT**: `monitor-pr/scripts/collect_comments.sh`를 실행하여 미처리 코멘트를 확인한다. 약식·축약 모니터링 지시에서도 본 단계 생략 불가.
   - `TOTAL > 0`이면 **반드시 `/triage-comments {PR_NUMBER}`를 호출**한다. default/overnight 모드 공통 규칙이며 예외가 없다.
2. **LISTENING**: `monitor-pr/scripts/watch.sh`를 포그라운드 Bash로 1회 호출한다. baseline 캐시 파일은 워크트리 루트의 `.monitor-pr-state.json`에 유지하여 호출 간 `(id, updatedAt)` 페어를 보존한다. 인터럽트 신호 파일은 같은 워크트리 루트의 `.monitor-interrupt`를 `INTERRUPT_FILE`로 전달한다 — 메인 세션이 모니터링 중 SendMessage 지시를 보낼 때 그 turn을 1 cycle 이내에 yield시키는 트리거다 (`monitor-pr/SKILL.md` §"Interrupt — 능동 지시 yield"). **이 호출은 `run_in_background: true` / `&` / `nohup` 어떤 형태도 사용하지 않는다 — 포그라운드 단일 점유가 본 phase의 차단력 그 자체다.**
   ```bash
   REPO=E5presso/spakky-framework PR_NUMBER={PR} \
     PREV_STATE_FILE={워크트리 경로}/.monitor-pr-state.json \
     INTERRUPT_FILE={워크트리 경로}/.monitor-interrupt \
     bash {MONITOR_PR_SKILL_DIR}/scripts/watch.sh
   ```
3. **분기 (EVENT consumer)**: `watch.sh`가 stdout으로 emit한 출력의 첫 줄(`EVENT` 또는 `DONE`)과 `reason` 값을 같은 turn 안에서 case로 분기하여 핸들러를 실행한다. **분기 없이 turn을 종료하면 EVENT가 dead code가 된다.** `reason=comments-changed`이면 출력의 `staleHandledIds=` 값을 `collect_comments.sh` 호출 시 `STALE_HANDLED_IDS` 환경변수로 그대로 전달하여 in-place 갱신된 코멘트가 재triage 대상으로 되돌아오게 한다. case 분기의 정확한 형태는 `monitor-pr/SKILL.md` §"EVENT consumer 루프" SSOT.
4. **재기동 또는 Phase 7/8 continuation**: EVENT 처리 후 **즉시 1번으로 복귀하여 `watch.sh`를 다시 호출한다.** `(id, updatedAt)` 캐시와 `reviewDecision` baseline은 모두 `watch.sh`가 자동으로 `.monitor-pr-state.json`에 영속하므로 호출자가 별도로 갱신·전달하지 않는다. DONE이면 Phase 7로 전환. `DONE reason=mergeable-clean`이면 `.process-state.json`에 `phase7_ready`를 기록한 뒤 Phase 7로 전환한다. `--auto-merge` 또는 autopilot 하위 실행이면 Phase 7에서 멈추지 않고 같은 turn 안에서 Phase 8까지 계속 수행한다. **`reason=interrupt`는 예외** — watch.sh를 재호출하지 않고 turn을 종료한다. 메인 세션 지시가 inbox로 배달되어 새 turn으로 호출자를 깨우면, 그 turn에서 지시를 처리한 뒤 1번(INIT)으로 복귀하여 watch.sh를 재개한다 (`monitor-pr/SKILL.md` §"Interrupt — 능동 지시 yield").

## 리뷰 코멘트 처리 (MUST)

코멘트가 1건이라도 감지되면 **반드시 `/triage-comments`**를 거쳐야 한다. 메인 에이전트/구현 에이전트가 코멘트를 보고 직접 코드를 수정하는 "무지성 반영"은 금지한다. 판단(수용/반론/보류)은 triage 스킬에서만 이루어지며, 수용으로 판단된 항목만 코드 수정에 반영한다.

**`--overnight` 모드 분기**:
- **본인(PR 작성자) 코멘트**: `/triage-comments`로 자동 처리 (수용 시 수정→재push, 반론 시 스레드 답글). 사용자 승인 없이 진행.
- **타인 코멘트**: 처리하지 않고 "사용자 수동 응답 대기" 큐에 쌓는다. 이 큐가 비어있지 않으면 Phase 7에 도달해도 "리뷰 대기" 상태로 반환한다.

## 종료 조건

PR의 merge button이 활성화된 상태 (`mergeState in (CLEAN, UNSTABLE)` + `reviewDecision=APPROVED` + `failedChecks=0`). overnight 모드에서는 타인 코멘트 큐가 비어있을 때만 Phase 7로 진행.

> **MUST**: **모든 required check가 pass**할 때까지 Phase 7로 넘어가지 않는다. `BLOCKED` 상태에서 Phase 7로 전환하면 병합이 불가능하다.
