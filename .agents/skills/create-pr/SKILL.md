---
name: create-pr
description: Spakky Framework PR을 생성합니다
argument-hint: "<ISSUE-NUMBER> [--acceptance-file PATH | --acceptance-missing] [--metadata-only PR-NUMBER]"
user-invocable: false
---

# PR 생성

1. `git diff develop...HEAD`로 변경 파일 확인
2. Conventional Commits 형식 타이틀 (scope는 `/commit` 스킬 참조)
   - **타이틀에 closes 대상 이슈 번호를 포함한다.** 예: `feat(rabbitmq): add dead letter queue support (#42)`
   - 이슈 번호는 커밋 메시지의 `(#N)` 또는 브랜치명(`feat/42` 등)에서 추출한다.
3. PR 내용을 마크다운으로 구성한다. `--acceptance-file PATH`가 있으면 해당 파일 내용을 그대로 "Acceptance Criteria (자가 grep)" 섹션으로 포함한다. `--acceptance-missing`이면 `acceptance_check: missing` 1줄을 포함한다. PASS/partial인데 파일이 없거나 섹션이 빠지면 PR 생성 금지.
4. 기본 mode는 즉시 `gh pr create` 실행. 사용자 승인 요청 금지 — 승인 게이트는 호출자 스킬의 Phase 2/7 정책만 따른다. `--metadata-only PR-NUMBER`면 live Pull API에서 authenticated same-repo·current-branch·exact-HEAD OPEN PR identity를 먼저 확인하고 `gh pr create`를 절대 호출하지 않는다.
5. 기본 mode와 `--metadata-only` mode 모두 PR 메타데이터를 idempotent 수렴시킨다:
   - **Assignee**: `gh pr edit {PR_NUMBER} --add-assignee @me`
   - **Label**: 변경 내용의 성격에 맞는 label을 선택하여 적용
     ```bash
     gh label list --limit 50  # 사용 가능한 label 확인
     gh pr edit {PR_NUMBER} --add-label "{LABELS}"
     ```
   - label은 exact `develop...HEAD` diff의 성격으로 다시 결정하고 `gh label list --limit 50`에 실제 존재하는 label만 사용한다. expected label이 0개면 성공으로 처리하지 않는다.
   - 적용 뒤 `gh api user`, `gh api repos/{OWNER}/{REPO}/issues/{PR_NUMBER}`, `gh api repos/{OWNER}/{REPO}/pulls/{PR_NUMBER}`를 다시 읽어 current user assignee, expected label 전부, same-repo·current-branch·exact-HEAD OPEN identity를 확인한다. 불일치하면 실패하며 호출자는 `pr_opened` 체크포인트를 기록하지 않는다.

PR 대상: $ARGUMENTS
