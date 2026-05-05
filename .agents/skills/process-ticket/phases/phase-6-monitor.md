# Phase 6: CI & 리뷰 모니터링

> **Phase 진입 ping** (sub-agent 한정): monitor 첫 호출 직전 1회 SendMessage(to: "team-lead", message: `phase: Phase 6 monitor | issue: <N> | monitor armed`). SKILL.md "Phase 전환 progress ping" SSOT. 본 ping은 §"절대 명령"의 "백그라운드 후 turn 종료" 안티패턴과 별개 — ping 송신은 단방향이며 즉시 monitor 포그라운드 호출로 진입한다.

> **절대 명령 (서브에이전트 본인 책무).** 너는(이 phase를 실행하는 서브에이전트) 자기 turn 안에서 직접 `monitor-pr` 스킬(또는 그 안의 watch 스크립트)을 포그라운드 Bash로 호출한다. monitor watch는 단일 Bash 호출 안에서 60초 sleep + 스냅샷 cycle을 무한 반복하며 EVENT 또는 DONE이 관찰될 때까지 블록한다 — 너의 turn은 스크립트가 종료할 때까지 그 호출이 점유한다. EVENT가 stdout으로 1회 emit되면 §"실행 루프"의 case 분기를 자기 turn 안에서 그대로 실행한 뒤 즉시 INIT으로 복귀하여 watch를 다시 호출한다. **DONE(`reason in {merged, mergeable-clean, closed-without-merge, awaiting-human-review}`)이 나올 때까지 너는 turn을 종료하지 않는다.**
>
> **DONE 즉시 정지 (terminal stop).** `reason in {merged, mergeable-clean, closed-without-merge, awaiting-human-review}`이 관찰되는 순간 본 phase는 종료다. **그 시점에 추가 watch / poll / `gh pr view` 호출을 금지한다** — `reason=merged`는 Phase 8 cleanup 1회 실행 후, `mergeable-clean`은 Phase 7 머지 게이트로, `closed-without-merge`는 결과 보고 후, `awaiting-human-review`는 `status: awaiting-review` + `pending_human_comments: <bot CH2 코멘트 URL>` 보고 후 즉시 turn 종료한다. "한 번 더 확인해서 안전하게" / "mergeStateStatus 재검증" / "다음 cycle에 변화가 있는지" 류 추가 호출은 머지 후 dead time을 누적시키는 안티패턴이며 본 절이 명시적으로 차단한다.
>
> **auto-merge continuation (S1/S7 회귀 차단).** `DONE reason=mergeable-clean`은 process-ticket 전체의 terminal 반환이 아니라 **Phase 6만의 terminal**이다. `--auto-merge` 또는 autopilot 하위 실행에서는 `phase7_ready` 기록 직후 같은 turn 안에서 Phase 7 `auto-merging` ping을 송신하고 Phase 8 squash merge + cleanup까지 동기 실행한다. `phase7_ready`만 기록한 채 `status: blocked` / `awaiting merge` / `merge approval required` / `status: awaiting-merge` / 산문 요약으로 turn을 종료하는 행위는 `monitor-stuck`/`merge-gate-stuck` 형식 위반이다. 이 경우 호출자(autopilot)가 재개할 수는 있지만, 본 phase 실행자는 fallback에 의존하지 말고 즉시 병합 경로를 계속 수행해야 한다.
>
> 다음 4가지 안티패턴은 본 phase에서 명시적으로 금지된다 (`monitor-pr` SKILL §"절대 명령" SSOT):
>
> 1. **백그라운드 후 turn 종료** — watch / Monitor / 외부 스크립트를 `&` / `nohup` / `run_in_background: true` / `ScheduleWakeup` / `CronCreate`로 띄운 뒤 "monitor armed" 같은 보고와 함께 turn 종료.
> 2. **외부 알림 위임** — "다음 cycle은 알림으로 도달할 것"·"사용자가 변화를 알려줄 것"으로 polling 책임을 outsourcing.
> 3. **1~2회 polling 후 종료** — 1~2 cycle 돌고 "CI 진행 중" / "변화 없음" / "오래 걸릴 것 같음"으로 turn 종료. 종료 조건은 시간이 아니라 `DONE` reason.
> 4. **EVENT consumer 부재** — watch 호출 후 stdout의 `reason` 값을 case 분기하지 않은 채 turn 종료.
>
> 아래 **외부 백그라운드 경로는 전부 금지**된다 — 이름이 다를 뿐 "에이전트 제어 밖에서 돌아가는 polling"이라는 본질이 같아 이벤트 누락·경로 우회·토큰 낭비가 반복된다:
>
> - `Monitor` 도구 (until-loop 포함 어떤 형태로도 금지)
> - `run_in_background: true` (Bash 도구) — watch도 반드시 포그라운드로 호출.
> - `ScheduleWakeup`
> - `CronCreate` 기반 주기 실행
> - 추가 `sleep`, 가변/증가 간격, exponent backoff
> - `gh pr view` / `gh pr checks`를 메인이 별도 호출 (스크립트가 단일 진실 원천)
>
> `Skill(monitor-pr, ...)` 서브스킬 호출은 이 프로젝트가 직접 관리하는 스킬이므로 허용된다 — 단, 해당 스킬이 내부적으로 위 금지 경로를 쓰면 안 된다. 호출자가 Bash로 watch 스크립트를 직접 실행해도 되고, `Skill(monitor-pr, "{PR}")`로 호출해도 된다.
>
> Bash `sleep` 차단 메시지가 "Monitor with until-loop"를 권장하더라도 **무시한다** — 이 프로젝트의 Phase 6에서는 해당 권고가 적용되지 않는다. monitor watch의 무한 루프는 단일 Bash tool 호출의 포그라운드 점유이지 백그라운드 polling이 아니다.

## 실행 루프 (서브에이전트 본인이 같은 turn 안에서 수행)

너는 다음 4단계를 자기 turn 안에서 순서대로 수행한다. 각 단계 사이에 turn을 종료하지 않는다. DONE이 관찰될 때까지 1↔4 루프를 반복한다.

1. **INIT**: `monitor-pr`의 코멘트 수집 단계를 실행하여 미처리 코멘트를 확인한다.
   - `TOTAL > 0`이면 **반드시 `/triage-comments {PR_NUMBER}`를 호출**한다. default/overnight 모드 공통 규칙이며 예외가 없다.
2. **LISTENING**: `monitor-pr`의 watch 단계를 포그라운드 Bash로 1회 호출한다. baseline 캐시 파일은 워크트리 루트의 `.monitor-pr-state.json`에 유지하여 호출 간 `(id, updatedAt)` 페어를 보존한다. **이 호출은 `run_in_background: true` / `&` / `nohup` 어떤 형태도 사용하지 않는다 — 포그라운드 단일 점유가 본 phase의 차단력 그 자체다.**
   ```bash
   REPO=$(gh repo view --json owner,name --jq '.owner.login + "/" + .name') \
   PR_NUMBER={PR} \
   PREV_STATE_FILE={워크트리 경로}/.monitor-pr-state.json \
   PREV_REVIEW_DECISION={직전 결과 또는 빈 값} \
     bash {MONITOR_PR_SKILL_DIR}/scripts/watch.sh
   ```
3. **분기 (EVENT consumer)**: watch가 stdout으로 emit한 출력의 첫 줄(`EVENT` 또는 `DONE`)과 `reason` 값을 같은 turn 안에서 case로 분기하여 핸들러를 실행한다. **분기 없이 turn을 종료하면 EVENT가 dead code가 된다.** `reason=comments-changed`이면 출력의 `staleHandledIds=` 값을 코멘트 수집 호출 시 `STALE_HANDLED_IDS` 환경변수로 그대로 전달하여 in-place 갱신된 코멘트가 재triage 대상으로 되돌아오게 한다. case 분기의 정확한 형태는 `monitor-pr` SKILL §"EVENT consumer 루프" SSOT.
4. **재기동 또는 Phase 7/8 continuation**: EVENT 처리 후 baseline을 갱신(`PREV_REVIEW_DECISION`만 직전 출력값으로 업데이트, `(id, updatedAt)` 캐시는 watch가 자동으로 `.monitor-pr-state.json`에 영속)하여 **즉시 1번으로 복귀하여 watch를 다시 호출한다.** `DONE reason=mergeable-clean`이면 `.process-state.json`에 `phase7_ready`를 기록한 뒤 Phase 7로 전환한다. `--auto-merge` 또는 autopilot 하위 실행이면 Phase 7에서 멈추지 않고 같은 turn 안에서 Phase 8까지 계속 수행한다. `DONE` 이후에는 추가 watch/poll을 돌리지 않는다.

`phase7_ready` 기록 형식:

```bash
wt=$(pwd) && ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
jq --arg t "$ts" \
  --argjson pr "$PR_NUMBER" \
  --arg m "$MERGE_STATE" \
  --argjson pending "$PENDING_CHECKS" \
  --argjson failed "$FAILED_CHECKS" \
  '.phase7_ready = {reason: "mergeable-clean", pr: $pr, mergeState: $m, pendingChecks: $pending, failedChecks: $failed} | .updated_at = $t' \
  "$wt/.process-state.json" > "$wt/.process-state.json.tmp" \
  && mv "$wt/.process-state.json.tmp" "$wt/.process-state.json"
```

## 리뷰 코멘트 처리 (MUST)

코멘트가 1건이라도 감지되면 **반드시 `/triage-comments`**을 거쳐야 한다. 메인 에이전트/구현 에이전트가 코멘트를 보고 직접 코드를 수정하는 "무지성 반영"은 금지한다. 판단(수용/반론)은 triage-comments 스킬에서만 이루어지며 ("보류" 카테고리 없음 — 결정 불가 시 default=수용), 수용으로 판단된 항목만 코드 수정에 반영한다.

**`--overnight` 모드 분기**:
- **본인(PR 작성자) 코멘트**: `/triage-comments`로 자동 처리 (수용 시 수정→재push, 반론 시 스레드 답글). 사용자 승인 없이 진행.
- **타인 코멘트**: 처리하지 않고 "사용자 수동 응답 대기" 큐에 쌓는다. 이 큐가 비어있지 않으면 Phase 7에 도달해도 "리뷰 대기" 상태로 반환한다.

## 종료 조건

PR의 merge button이 활성화된 상태 (`mergeState in (CLEAN, UNSTABLE)` + `pendingChecks=0` + `failedChecks=0`)이며, 외부 리뷰 봇(`REVIEW_BOT_LOGINS`, 기본 `claude[bot],codex[bot],chatgpt-codex-connector[bot]`)이 현재 HEAD를 평가했다. GitHub Copilot/Codex code review는 formal Approve를 남기지 않으므로 `reviewDecision=APPROVED`를 요구하지 않는다. 실제 branch protection상 human approval이 필수라면 GitHub가 `mergeState=BLOCKED`로 노출한다. overnight 모드에서는 타인 코멘트 큐가 비어있을 때만 Phase 7로 진행.

Codecov PR coverage report처럼 required check와 중복되는 정보성 봇 코멘트는 Phase 7 전환을 막지 않는다. 실패 여부는 `failedChecks`가 담당하며, green CI 상태에서 coverage report의 신규/갱신 코멘트만으로 `/triage-comments` 루프에 재진입하지 않는다.

> **MUST**: GitHub Actions / 모든 required check가 pass하고 review bot HEAD 평가가 끝날 때까지 Phase 7로 넘어가지 않는다. `BLOCKED` 상태에서 Phase 7로 전환하면 병합이 불가능하다. 자동화 봇 리뷰어가 pending이면 MERGEABLE 판정 보류 (메모리 `bc25934` 회귀).
