# Phase 5: 커밋 & PR 생성

> **자동 진행**: 이 Phase는 사용자 확인 없이 전부 자동 실행한다.

> **Phase 진입 ping** (sub-agent 한정): `/create-pr` 성공 직후 1회 SendMessage(to: "team-lead", message: `phase: Phase 5 commit-pr | issue: <N> | PR #<N> opened`). SKILL.md "Phase 전환 progress ping" SSOT.

1. **root-worktree mutation guard (commit 차단)** — 커밋/포맷/push/PR 생성 전에 워크트리 cwd에서 다음을 실행한다:
   ```bash
   bash .agents/skills/process-ticket/scripts/assert_worktree_isolation.sh {ISSUE-NUMBER}
   ```
   실패하면 Phase 5를 중단하고 `.process-state.json.failed = {"phase":"Phase 5 isolation","reason":"<isolation-failed 1줄>"}`로 기록한다. root dirty를 되돌리지 않는다.
2. 커밋 전 `ruff format`을 선행하여 hook 실패를 예방한다.
3. **post-format isolation 재검증** — 포맷터가 잘못된 cwd에서 root checkout을 변경한 케이스를 commit 전에 잡기 위해 1번 guard를 다시 실행한다.
4. `/commit` 서브스킬을 실행하여 Conventional Commits 형식으로 커밋한다.
5. **체크포인트 갱신** — `.process-state.json`에 `commit_done` 기록 (SKILL.md "상태 핸드오프" 참조):
   ```bash
   wt=$(pwd) && ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ") && hash=$(git rev-parse HEAD)
   jq --arg h "$hash" --arg t "$ts" '.commit_done = $h | .updated_at = $t' "$wt/.process-state.json" > "$wt/.process-state.json.tmp" && mv "$wt/.process-state.json.tmp" "$wt/.process-state.json"
   ```
6. 리모트에 push한다:
   ```bash
   git push -u origin HEAD
   ```
   push 직후 `git rev-parse HEAD`와 `git rev-parse @{u}`를 비교하여 remote 반영을 검증한다 (`behavioral-guidelines.md` §3 "git push 후 remote 반영을 반드시 검증").
7. **체크포인트 갱신** — `.process-state.json`에 `push_done` 기록:
   ```bash
   wt=$(pwd) && ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ") && ref=$(git symbolic-ref HEAD)
   jq --arg r "$ref" --arg t "$ts" '.push_done = $r | .updated_at = $t' "$wt/.process-state.json" > "$wt/.process-state.json.tmp" && mv "$wt/.process-state.json.tmp" "$wt/.process-state.json"
   ```
8. `/create-pr {ISSUE-NUMBER}` 서브스킬을 실행하여 PR을 생성한다. PR 타이틀에 `(#<ISSUE-NUMBER>)` 포함 필수. 한글 타이틀은 heredoc 이스케이프 버그 회피를 위해 `--title` 단일 인자로 전달한다.
9. **체크포인트 갱신** — `.process-state.json`에 `pr_opened` 기록 (PR 번호와 URL):
   ```bash
   wt=$(pwd) && ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
   pr_num={PR_NUMBER}  # /create-pr 반환값
   pr_url={PR_URL}
   jq --argjson n "$pr_num" --arg u "$pr_url" --arg t "$ts" '.pr_opened = {number: $n, url: $u} | .updated_at = $t' "$wt/.process-state.json" > "$wt/.process-state.json.tmp" && mv "$wt/.process-state.json.tmp" "$wt/.process-state.json"
   ```
10. **프로젝트 상태 갱신 (명시적 호출 — silent 누락 금지)** — 서브에이전트로 `/update-project-status {ISSUE-NUMBER} "In Review"` 실행. 결과 stdout 1줄을 회수하여 실패·경고 관찰 시 메인 stdout에 `project-status-update-failed: In Review <원인>` 1줄 기록 + 최종 반환 `notes:` 라인에 누적한다. 본 작업은 차단하지 않는다 (SKILL.md "GitHub 이슈/프로젝트 상태 자동 전이" 참조).
