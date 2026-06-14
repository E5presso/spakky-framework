# Phase 8: 병합 & 정리

> **Phase 진입 ping** (sub-agent 한정): `gh pr merge` 성공 직후 1회 SendMessage(to: "team-lead", message: `phase: Phase 8 cleanup | issue: <id> | merged, sweeping`). SKILL.md "Phase 전환 progress ping" SSOT.

사용자가 병합을 승인하면 (또는 `--auto-merge`로 사전 승인된 경우) 아래를 **순서대로 동기 실행**한다. 머지 명령 직후 서브에이전트가 종료되면 후속 cleanup이 누락되어 머지 완료 PR이 워크트리·로컬 브랜치를 남긴 채 종료되므로, 1~7단계를 모두 마치기 전에 서브에이전트가 종료해서는 안 된다.

본 cleanup은 **idempotent**하다 — 각 단계는 이미 정리된 상태에서 재실행해도 정상 종료한다. 실패해도 후속 단계는 시도한다 (silent skip 금지, 실패 사유는 누적 후 사용자에게 보고).

사전: `WORKTREE_ABS`는 Phase 3에서 반환된 워크트리 절대경로. 본 phase의 모든 git 명령은 `git -C "$WORKTREE_ABS" <subcommand>` 또는 `git -C "$REPO_ROOT" worktree ...` 패턴을 사용하며 `cd`로 호출자 프로세스 cwd를 변이시키지 않는다 (`worktree-isolation.md` SSOT).

> **단계 순서 (sub-agent 한정 — terminal 반환 ↔ 워크트리 정리 분리).** 순서는 **머지(§1) → 체크포인트(§2) → GitHub 전이(§3·§3-bis) → terminal 반환 emit(§4) → 워크트리 정리(§5) → develop 최신화·확인·보고(§6~§8)** (§5는 메인 핸드오프 왕복 — 반환을 그 뒤에 두면 회신 유실 시 반환이 영영 emit되지 않는 단일 실패점).

## 1. PR 병합

```bash
gh pr merge {PR_NUMBER} --repo E5presso/spakky-framework --squash --delete-branch
```

`--delete-branch`는 **remote 브랜치만** 삭제한다. 로컬 워크트리·로컬 브랜치는 5단계로 별도 정리한다.

## 2. 체크포인트 갱신 — `merged` 기록 (SKILL.md "상태 핸드오프" 참조)

```bash
ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ") && merge_sha=$(gh pr view {PR_NUMBER} --repo E5presso/spakky-framework --json mergeCommit --jq '.mergeCommit.oid')
jq --arg s "$merge_sha" --arg t "$ts" '.merged = $s | .updated_at = $t' "$WORKTREE_ABS/.process-state.json" > "$WORKTREE_ABS/.process-state.json.tmp" && mv "$WORKTREE_ABS/.process-state.json.tmp" "$WORKTREE_ABS/.process-state.json"
```

## 3. 이슈/프로젝트 상태 갱신 (명시적 호출 — silent 누락 금지)

서브에이전트로 `/update-project-status {ISSUE-NUMBER} Done` 실행. 결과 stdout 1줄을 회수하여 실패·경고 관찰 시 메인 stdout에 `project-status-update-failed: Done <원인>` 1줄 기록 + 최종 반환 `notes:` 라인에 누적한다. 본 작업은 차단하지 않는다 (SKILL.md "GitHub Issue 상태 자동 전이" 참조).

## 3-bis. GitHub 상태 전이 검증 (자기 보고 silent corruption 차단)

`/update-project-status`가 silent failure 했거나 verification-only no-op 케이스에서 갱신이 누락되어도 호출자는 알 수 없다. 본 절은 머지 직후 GitHub를 직접 재조회하여 자기 보고와 사실의 어긋남을 차단한다.

```
gh issue view 또는 GitHub connector 조회({ id: "{ISSUE-NUMBER}" }) → status, statusType
```

분기:

1. `statusType == "completed"` (Done) 또는 `statusType == "canceled"` (Cancelled) → 정상 종료. 본 절은 차단하지 않는다.
2. 그 외 (`backlog` / `unstarted` / `started`) → `gh issue edit 또는 GitHub connector 갱신({ id, state: "Done" })`로 강제 전이 + 재조회로 검증.
3. 강제 전이 후에도 `statusType != "completed"` → 메인 stdout에 1줄 기록: `github-status-transition-failed: <전이 시도 명> <실제 statusType>`. 본 스킬 종료 시 반환 형식의 `issue_status` 필드는 **실제 조회한 statusType을 그대로 반영**한다 (낙관적 `Done` 보고 금지). autopilot은 `status: merged`인데 `issue_status != Done`이면 alert 분기 진입.

본 검증은 verification-only no-op 케이스(머지할 PR이 없고 검증만 수행한 케이스)에도 동일하게 적용한다 — 그 케이스는 §1 PR 머지를 건너뛰지만 본 §3-bis는 동일 phase 경계로 실행하여 GitHub Done 전이를 강제한다.

## 4. 정규형 terminal 반환 emit (워크트리 정리보다 먼저 — sub-agent 한정)

sub-agent로 실행 중이면(team_name 발급) **이 시점에 SKILL.md "서브에이전트 반환 형식 (강제)" 정규형 terminal 반환을 `SendMessage(to: "team-lead", summary: "terminal-return {ISSUE-NUMBER}", message: <정규형 본문>)`로 emit한다** — 아래 §5 워크트리 정리 핸드오프보다 **먼저**다.

근거 (채널): background teammate는 plain text 출력을 호출자에게 자동 전달하지 않는다 — `SendMessage` 채널 강제 (SKILL.md "서브에이전트 반환 형식 (강제)" §"전달 채널" SSOT).

근거 (순서): 반환은 cleanup 완료에 논리적으로 무관 (cleanup은 idempotent + sub-agent 경로에서 메인 소유) — 핸드오프 왕복 뒤에 두면 단일 실패점.

- 반환 정규형의 `status` / `pr` / `ticket` / `acceptance_check` / `issue_status` / `spawned` / `gaps_detected` / `gaps_dispatched` 라인을 모두 포함한다. `issue_status`는 §3-bis에서 실제 조회한 statusType을 그대로 반영한다.
- terminal 반환 emit 후에도 turn을 종료하지 않는다 — §5~§8을 이어서 수행한다. §5 워크트리 정리 핸드오프의 메인 회신(`worktree-removed`) 수신까지 마친 뒤에 turn을 종료한다.
- 사용자 직접 호출(메인이 곧 사용자 채널)에서는 별도 정규형 emit 대신 §8 최종 완료 보고가 동등 역할을 한다 — 본 §4를 건너뛰고 §5로 진행한다.

## 5. 로컬 워크트리·브랜치 정리 (idempotent 강제)

머지 직후 워크트리·로컬 브랜치를 정리한다. **`ExitWorktree` 도구 호출 금지** — 도구가 부모/형제 sub-agent 프로세스 cwd를 변이시킨다. `git worktree remove --force`가 단일 정리 수단이다.

정리 주체는 호출 경로에 따라 갈린다 — sub-agent는 자기가 들어가 있는 워크트리를 직접 제거할 수 없다 (git이 in-use 워크트리 제거를 거부하며, 제거 즉시 sub-agent의 도구 경로가 무효가 된다). 따라서:

### 5-A. 사용자 직접 호출 경로 (`/process-ticket` 직접 실행)

메인 세션이 곧 호출자이므로 워크트리를 직접 제거한다. 아래 3단계는 **idempotent**: 이미 정리된 상태에서 재실행해도 정상 종료해야 한다 (워크트리 부재·브랜치 부재·state 키 부재 모두 정상).

```bash
branch=$(git -C "$WORKTREE_ABS" branch --show-current)
REPO_ROOT=$(git -C "$WORKTREE_ABS" rev-parse --path-format=absolute --git-common-dir | sed 's|/\.git$||')

# (a) 워크트리 remove (force) — 이미 제거되었으면 정상 종료로 간주
git -C "$REPO_ROOT" worktree remove "$WORKTREE_ABS" --force 2>&1 | tee /tmp/cleanup-wt.log
wt_rc=${PIPESTATUS[0]}
if [ "$wt_rc" -ne 0 ] && ! grep -q "is not a working tree" /tmp/cleanup-wt.log; then
  echo "cleanup-failed: worktree-remove $(cat /tmp/cleanup-wt.log)"
fi

# (b) 로컬 브랜치 삭제 — 이미 없으면 정상 종료로 간주
git -C "$REPO_ROOT" branch -D "$branch" 2>&1 | tee /tmp/cleanup-br.log
br_rc=${PIPESTATUS[0]}
if [ "$br_rc" -ne 0 ] && ! grep -q "not found" /tmp/cleanup-br.log; then
  echo "cleanup-failed: branch-delete $(cat /tmp/cleanup-br.log)"
fi

# (c) state에 cleaned=true 기록 (워크트리가 (a)에서 제거됐으면 skip)
if [ -f "$WORKTREE_ABS/.process-state.json" ]; then
  ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  jq --arg t "$ts" '.cleaned = true | .updated_at = $t' "$WORKTREE_ABS/.process-state.json" > "$WORKTREE_ABS/.process-state.json.tmp" && mv "$WORKTREE_ABS/.process-state.json.tmp" "$WORKTREE_ABS/.process-state.json" || echo "cleanup-failed: state-write"
fi
```

세 단계 중 하나라도 실패하면 메인 stdout에 `cleanup-failed: <stage> <원인>` 1줄을 기록하고 최종 반환 `notes:` 라인에 누적한다. 본 cleanup은 머지 자체를 차단하지 않지만 **묵시적 누락은 금지** — 누락이 누적되면 잔존 워크트리가 다음 세션의 작업 영역을 오염시킨다 (autopilot SKILL.md "Phase 6.5 잔존 워크트리 sweep" 외부 안전망과 짝을 이룬다).

### 5-B. sub-agent 경로 (autopilot 등이 spawn — `team_name` 발급)

sub-agent는 자기 워크트리를 직접 제거할 수 없으므로 메인(team-lead)에 정리를 핸드오프한다.

1. 메인에 정리 요청을 송신한다:
   ```
   SendMessage(to: "team-lead", summary: "worktree-cleanup-req {ISSUE-NUMBER}",
     message: "worktree-cleanup-req: {ISSUE-NUMBER} | worktree=$WORKTREE_ABS | branch=<branch>")
   ```
2. **`worktree-cleanup-req` 송신은 sub-agent의 마지막 행위가 아니다.** 메인이 워크트리·로컬 브랜치를 제거하고 `worktree-removed: {ISSUE-NUMBER}` 회신을 보낼 때까지 turn을 종료하지 않는다 (회신은 자동 delivery). cleanup-req 송신 직후 idle 진입은 금지 — autopilot 메인이 잔존 워크트리 sweep을 떠맡게 되어 본 phase의 정리 책임이 누락된다.
3. 메인의 `worktree-removed` 회신을 수신하면 **그것으로 turn을 종료한다**. 정규형 terminal 반환은 §4에서 이미 emit되었으므로 회신 수신 후 추가로 emit할 반환은 없다 — §4가 핸드오프 왕복 앞에 있는 이유가 이것이며, 회신 수신을 새 반환 emit 트리거로 오해하지 않는다. §6~§7(develop 최신화·병합 확인)은 sub-agent 경로에서는 메인이 정리 후 수행하므로 sub-agent는 §8 보고를 생략하고 turn을 종료한다.

## 6. 메인 리포 develop 최신화

```bash
git -C "$REPO_ROOT" checkout develop
git -C "$REPO_ROOT" pull origin develop
```

`cd`로 호출자 프로세스 cwd를 메인 리포로 옮기지 않는다 — `git -C` 패턴으로 명령 단위 디렉토리 지정. 사용자 직접 호출 경로(§5-A)에서는 (a)에서 워크트리가 이미 제거되었으므로 메인 세션의 cwd가 더 이상 워크트리에 박혀 있지 않아 안전하다. sub-agent 경로(§5-B)에서는 본 단계를 메인 세션이 워크트리 제거 직후 수행한다.

## 7. 병합 확인

```bash
git log --oneline -5
```

병합한 커밋이 develop에 정상 반영되었는지 확인한다.

## 8. 사용자에게 최종 완료 보고

사용자 직접 호출 경로에서만 수행한다 (sub-agent 경로는 §4 정규형 terminal 반환이 동등 역할 — §5-B 3 참조).

```
## 작업 완료

이슈: {ISSUE-NUMBER}
PR: {PR_URL} (merged)
커밋: {COMMIT_SHA}
acceptance_check: {PASS|partial|missing}
issue_status: {Done|...} (GitHub 실제 조회 결과)
cleanup: ok | failed (<stage>: <원인>)
```

## 회피 패턴 금지

- **직렬화·병렬 축소로 풀지 않는다**: 본 fix는 "서브에이전트가 머지 명령 후 즉시 종료하지 말고 cleanup을 동기 실행하라"는 동작 강제이지, 병렬 PR 머지를 직렬화하여 회피하는 것이 아니다.
- **`ExitWorktree` 도구 호출 금지**: 도구가 부모/형제 sub-agent 프로세스 cwd를 변이시킨다. §5-A (a) `git worktree remove --force`가 단일 정리 수단이며, 본 phase 어느 단계에서도 `ExitWorktree`를 호출하지 않는다.
- **`--delete-branch` 단독 의존 금지**: remote만 삭제되며 로컬은 남는다. §5-A (b)가 로컬 정리를 보장한다.
- **terminal 반환을 워크트리 정리 뒤로 미루지 않는다**: §4는 §5 핸드오프보다 먼저다. cleanup-req 송신을 turn 종료 시그널로 간주하거나, `worktree-removed` 회신 수신을 반환 emit 트리거로 오해하는 것은 본 phase가 명시적으로 차단하는 안티패턴이다.
