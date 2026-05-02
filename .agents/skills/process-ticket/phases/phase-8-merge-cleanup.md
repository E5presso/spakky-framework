# Phase 8: 병합 & 정리

> **Phase 진입 ping** (sub-agent 한정): `gh pr merge` 성공 직후 1회 SendMessage(to: "team-lead", message: `phase: Phase 8 cleanup | issue: <N> | merged, sweeping`). SKILL.md "Phase 전환 progress ping" SSOT.

사용자가 병합을 승인하면 (또는 `--auto-merge`로 사전 승인된 경우) 아래를 **순서대로 동기 실행**한다. 머지 명령 직후 서브에이전트가 종료되면 후속 cleanup이 누락되어 머지 완료 PR이 워크트리·로컬 브랜치를 남긴 채 종료되므로, 1~7단계를 모두 마치기 전에 서브에이전트가 종료해서는 안 된다.

본 cleanup은 **idempotent**하다 — 각 단계는 이미 정리된 상태에서 재실행해도 정상 종료한다. 실패해도 후속 단계는 시도한다 (silent skip 금지, 실패 사유는 누적 후 사용자에게 보고).

## 1. PR 병합

```bash
REPO=$(gh repo view --json owner,name --jq '.owner.login + "/" + .name')
gh pr merge {PR_NUMBER} --repo "$REPO" --squash --delete-branch
```

`--delete-branch`는 **remote 브랜치만** 삭제한다. 로컬 워크트리·로컬 브랜치는 4단계로 별도 정리한다. `--admin`·`--auto` 절대 금지.

## 2. 체크포인트 갱신 — `merged` 기록 (SKILL.md "상태 핸드오프" 참조)

```bash
wt=$(pwd) && ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
merge_sha=$(gh pr view {PR_NUMBER} --repo "$REPO" --json mergeCommit --jq '.mergeCommit.oid')
jq --arg s "$merge_sha" --arg t "$ts" '.merged = $s | .updated_at = $t' "$wt/.process-state.json" > "$wt/.process-state.json.tmp" && mv "$wt/.process-state.json.tmp" "$wt/.process-state.json"
```

## 3. 프로젝트 상태 갱신 + 이슈 close (명시적 호출 — silent 누락 금지)

서브에이전트로 `/update-project-status {ISSUE-NUMBER} "Done"` 실행 후 `gh issue close {ISSUE-NUMBER}` 실행. 결과 stdout 1줄을 회수하여 실패·경고 관찰 시 메인 stdout에 `project-status-update-failed: Done <원인>` 1줄 기록 + 최종 반환 `notes:` 라인에 누적한다. 본 작업은 차단하지 않는다 (SKILL.md "GitHub 이슈/프로젝트 상태 자동 전이" 참조).

## 3-bis. 이슈 상태 전이 검증 (자기 보고 silent corruption 차단)

`/update-project-status`가 silent failure 했거나 verification-only no-op 케이스에서 갱신이 누락되어도 호출자는 알 수 없다. 본 절은 머지 직후 GitHub을 직접 재조회하여 자기 보고와 사실의 어긋남을 차단한다.

```bash
state=$(gh issue view {ISSUE-NUMBER} --json state --jq '.state')
```

분기:

1. `state == "CLOSED"` → 정상 종료. 본 절은 차단하지 않는다.
2. 그 외 (`OPEN`) → `gh issue close {ISSUE-NUMBER}`로 강제 전이 + 재조회로 검증.
3. 강제 전이 후에도 `state != "CLOSED"` → 메인 stdout에 1줄 기록: `issue-state-transition-failed: <전이 시도 명> <실제 state>`. 본 스킬 종료 시 반환 형식의 `issue_status` 필드는 **실제 조회한 state를 그대로 반영**한다 (낙관적 `Done` 보고 금지). autopilot은 `status: merged`인데 `issue_status != Done`이면 alert 분기 진입.

본 검증은 verification-only no-op 케이스(머지할 PR이 없고 검증만 수행한 케이스)에도 동일하게 적용한다 — 그 케이스는 §1 PR 머지를 건너뛰지만 본 §3-bis는 동일 phase 경계로 실행하여 close 전이를 강제한다.

## 4. 로컬 워크트리·브랜치 동기 정리 (idempotent 강제)

머지 직후 다음 3단계를 **서브에이전트 종료 전에** 동기 실행한다. 본 단계는 `ExitWorktree` 도구 호출에만 의존하지 않는다 — 서브에이전트가 그 호출 전에 종료하면 누락되기 때문이다.

각 단계는 **idempotent**: 이미 정리된 상태에서 재실행해도 정상 종료해야 한다 (워크트리 부재·브랜치 부재·state 키 부재 모두 정상).

```bash
wt=$(pwd)
branch=$(git branch --show-current)
repo_root=$(git -C "$wt" rev-parse --path-format=absolute --git-common-dir | xargs dirname)

# (a) 워크트리 remove (force) — 이미 제거되었으면 정상 종료로 간주
git -C "$repo_root" worktree remove "$wt" --force 2>&1 | tee /tmp/cleanup-wt.log
wt_rc=${PIPESTATUS[0]}
if [ "$wt_rc" -ne 0 ] && ! grep -q "is not a working tree" /tmp/cleanup-wt.log; then
  echo "cleanup-failed: worktree-remove $(cat /tmp/cleanup-wt.log)"
fi

# (b) 로컬 브랜치 삭제 — 이미 없으면 정상 종료로 간주
git -C "$repo_root" branch -D "$branch" 2>&1 | tee /tmp/cleanup-br.log
br_rc=${PIPESTATUS[0]}
if [ "$br_rc" -ne 0 ] && ! grep -q "not found" /tmp/cleanup-br.log; then
  echo "cleanup-failed: branch-delete $(cat /tmp/cleanup-br.log)"
fi

# (c) state에 cleaned=true 기록 (워크트리가 (a)에서 제거됐으면 skip)
if [ -f "$wt/.process-state.json" ]; then
  ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  jq --arg t "$ts" '.cleaned = true | .updated_at = $t' "$wt/.process-state.json" > "$wt/.process-state.json.tmp" && mv "$wt/.process-state.json.tmp" "$wt/.process-state.json" || echo "cleanup-failed: state-write"
fi
```

세 단계 중 하나라도 실패하면 메인 stdout에 `cleanup-failed: <stage> <원인>` 1줄을 기록하고 최종 반환 `notes:` 라인에 누적한다. 본 cleanup은 머지 자체를 차단하지 않지만 **묵시적 누락은 금지** — 누락이 누적되면 잔존 워크트리가 다음 세션의 작업 영역을 오염시킨다 (autopilot 잔존 워크트리 sweep 외부 안전망과 짝을 이룬다).

## 5. 메인 리포 develop 최신화

```bash
cd "$repo_root" && git checkout develop && git pull origin develop
```

`ExitWorktree` 도구를 호출 가능한 컨텍스트(메인 세션이 EnterWorktree로 진입한 케이스)이면 `ExitWorktree(action: "remove")`를 호출하여 세션 cwd를 메인 리포로 복원한다. 서브에이전트 cwd-override 컨텍스트(EnterWorktree 미진입 케이스)에서는 4-(a)에서 이미 워크트리가 제거되었으므로 본 도구 호출은 불필요·금지.

## 6. 병합 확인

```bash
git log --oneline -5
```

병합한 커밋이 develop에 정상 반영되었는지 확인한다.

## 7. 사용자에게 최종 완료 보고

```
## 작업 완료

이슈: #{ISSUE-NUMBER}
PR: {PR_URL} (merged)
커밋: {COMMIT_SHA}
acceptance_check: {PASS|partial|missing}
issue_status: {Done|...} (GitHub 실제 조회 결과)
cleanup: ok | failed (<stage>: <원인>)
```

## 회피 패턴 금지

- **직렬화·병렬 축소로 풀지 않는다**: 본 fix는 "서브에이전트가 머지 명령 후 즉시 종료하지 말고 cleanup을 동기 실행하라"는 동작 강제이지, 병렬 PR 머지를 직렬화하여 회피하는 것이 아니다.
- **`ExitWorktree` 도구 단독 의존 금지**: 도구 호출은 EnterWorktree 컨텍스트에만 동작하며, 서브에이전트가 그 호출 전에 종료하면 누락된다. 4-(a) `git worktree remove --force`가 1차 정리 수단이다.
- **`--delete-branch` 단독 의존 금지**: remote만 삭제되며 로컬은 남는다. 4-(b)가 로컬 정리를 보장한다.
