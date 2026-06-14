# Phase 5: 커밋 & PR 생성

> **자동 진행**: 이 Phase는 사용자 확인 없이 전부 자동 실행한다.

> **Phase 진입 ping** (sub-agent 한정): `/create-pr` 성공 직후 1회 SendMessage(to: "team-lead", message: `phase: Phase 5 commit-pr | issue: <id> | PR #<N> opened`). SKILL.md "Phase 전환 progress ping" SSOT. 첫 commit 직전 `commit-start`·push 검증 직후 `push-done` ping은 SKILL.md "commit-start / push-done ping" SSOT.

0. **Integration / e2e 는 GitHub Actions 위임 (commit 진입 전 실행 금지)** — `mise run //:ci` SSOT 정의("Run CI checks (unit + lint; integration/e2e is covered by GitHub Actions on PR and develop)") 그대로 commit 진입 전에는 `mise run :ci`(unit + lint) 만 실행한다. pre-commit hook (`ops/scripts/pre-commit-ci.sh`) 이 자동 호출하므로 본 phase 에서 별도 명시 호출 불필요. Integration / e2e 회귀는 PR open 후 GitHub Actions required checks 가 책임지며, 본 phase 의 sub-agent 가 `mise run :test_integration` 등을 commit 진입 전 게이트로 실행하지 않는다. `tests/integration/` 직접 수정 케이스도 동일 — 회귀는 GitHub Actions 게이트가 차단한다.
1. `/commit` 서브스킬을 실행하여 커밋한다.
2. **체크포인트 갱신** — `.process-state.json`에 `commit_done` 기록 (SKILL.md "상태 핸드오프" 참조):
   ```bash
   wt=$(pwd) && ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ") && hash=$(git rev-parse HEAD)
   jq --arg h "$hash" --arg t "$ts" '.commit_done = $h | .updated_at = $t' "$wt/.process-state.json" > "$wt/.process-state.json.tmp" && mv "$wt/.process-state.json.tmp" "$wt/.process-state.json"
   ```
3. 리모트에 push한다:
   ```bash
   git push -u origin HEAD
   ```
4. **체크포인트 갱신** — `.process-state.json`에 `push_done` 기록:
   ```bash
   wt=$(pwd) && ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ") && ref=$(git symbolic-ref HEAD)
   jq --arg r "$ref" --arg t "$ts" '.push_done = $r | .updated_at = $t' "$wt/.process-state.json" > "$wt/.process-state.json.tmp" && mv "$wt/.process-state.json.tmp" "$wt/.process-state.json"
   ```
5. `/create-pr {ISSUE-NUMBER}` 서브스킬을 실행하여 PR을 생성한다.
6. **체크포인트 갱신** — `.process-state.json`에 `pr_opened` 기록 (PR 번호와 URL):
   ```bash
   wt=$(pwd) && ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
   pr_num={PR_NUMBER}  # /create-pr 반환값
   pr_url={PR_URL}
   jq --argjson n "$pr_num" --arg u "$pr_url" --arg t "$ts" '.pr_opened = {number: $n, url: $u} | .updated_at = $t' "$wt/.process-state.json" > "$wt/.process-state.json.tmp" && mv "$wt/.process-state.json.tmp" "$wt/.process-state.json"
   ```
7. **이슈/프로젝트 상태 갱신 (명시적 호출 — silent 누락 금지)** — 서브에이전트로 `/update-project-status {ISSUE-NUMBER} In Review` 실행. 결과 stdout 1줄을 회수하여 실패·경고 관찰 시 메인 stdout에 `project-status-update-failed: In Review <원인>` 1줄 기록 + 최종 반환 `notes:` 라인에 누적한다. 본 작업은 차단하지 않는다 (SKILL.md "GitHub Issue 상태 자동 전이" 참조).
