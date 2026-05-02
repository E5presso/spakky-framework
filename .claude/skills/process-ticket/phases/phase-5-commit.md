# Phase 5: 커밋 & PR 생성

> **자동 진행**: 이 Phase는 사용자 확인 없이 전부 자동 실행한다.

> **Phase 진입 ping** (sub-agent 한정): `/create-pr` 성공 직후 1회 SendMessage(to: "team-lead", message: `phase: Phase 5 commit-pr | issue: <N> | PR #<N> opened`). SKILL.md "Phase 전환 progress ping" SSOT.

1. 커밋 전 `ruff format`을 선행하여 hook 실패를 예방한다 (메모리 `feedback_preformat_before_commit.md`).
2. `/commit` 서브스킬을 실행하여 Conventional Commits 형식으로 커밋한다.
3. **체크포인트 갱신** — `.process-state.json`에 `commit_done` 기록 (SKILL.md "상태 핸드오프" 참조):
   ```bash
   wt=$(pwd) && ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ") && hash=$(git rev-parse HEAD)
   jq --arg h "$hash" --arg t "$ts" '.commit_done = $h | .updated_at = $t' "$wt/.process-state.json" > "$wt/.process-state.json.tmp" && mv "$wt/.process-state.json.tmp" "$wt/.process-state.json"
   ```
4. 리모트에 push한다:
   ```bash
   git push -u origin HEAD
   ```
   push 직후 `git rev-parse HEAD`와 `git rev-parse @{u}`를 비교하여 remote 반영을 검증한다 (`behavioral-guidelines.md` §3 "git push 후 remote 반영을 반드시 검증").
5. **체크포인트 갱신** — `.process-state.json`에 `push_done` 기록:
   ```bash
   wt=$(pwd) && ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ") && ref=$(git symbolic-ref HEAD)
   jq --arg r "$ref" --arg t "$ts" '.push_done = $r | .updated_at = $t' "$wt/.process-state.json" > "$wt/.process-state.json.tmp" && mv "$wt/.process-state.json.tmp" "$wt/.process-state.json"
   ```
6. `/create-pr {ISSUE-NUMBER}` 서브스킬을 실행하여 PR을 생성한다. PR 타이틀에 `(#<ISSUE-NUMBER>)` 포함 필수 (메모리 `feedback_pr_title_issue_number.md`). 한글 타이틀은 `--title` 단일 인자로 전달 (메모리 `feedback_pr_title_korean_encoding.md`).
7. **체크포인트 갱신** — `.process-state.json`에 `pr_opened` 기록 (PR 번호와 URL):
   ```bash
   wt=$(pwd) && ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
   pr_num={PR_NUMBER}  # /create-pr 반환값
   pr_url={PR_URL}
   jq --argjson n "$pr_num" --arg u "$pr_url" --arg t "$ts" '.pr_opened = {number: $n, url: $u} | .updated_at = $t' "$wt/.process-state.json" > "$wt/.process-state.json.tmp" && mv "$wt/.process-state.json.tmp" "$wt/.process-state.json"
   ```
8. **프로젝트 상태 갱신 (명시적 호출 — silent 누락 금지)** — 서브에이전트로 `/update-project-status {ISSUE-NUMBER} "In Review"` 실행. 결과 stdout 1줄을 회수하여 실패·경고 관찰 시 메인 stdout에 `project-status-update-failed: In Review <원인>` 1줄 기록 + 최종 반환 `notes:` 라인에 누적한다. 본 작업은 차단하지 않는다 (SKILL.md "GitHub 이슈/프로젝트 상태 자동 전이" 참조).
