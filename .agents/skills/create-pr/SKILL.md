---
name: create-pr
description: Spakky Framework PR을 생성합니다
argument-hint: "<ISSUE-NUMBER> [--acceptance-file PATH | --acceptance-missing]"
user-invocable: false
---

# PR 생성

1. `git diff develop...HEAD`로 변경 파일 확인
2. Conventional Commits 형식 타이틀 (scope는 `/commit` 스킬 참조)
   - **타이틀에 closes 대상 이슈 번호를 포함한다.** 예: `feat(rabbitmq): add dead letter queue support (#42)`
   - 이슈 번호는 커밋 메시지의 `(#N)` 또는 브랜치명(`feat/42` 등)에서 추출한다.
3. PR 내용을 마크다운으로 구성한다. `--acceptance-file PATH`가 있으면 해당 파일 내용을 그대로 "Acceptance Criteria (자가 grep)" 섹션으로 포함한다. `--acceptance-missing`이면 `acceptance_check: missing` 1줄을 포함한다. PASS/partial인데 파일이 없거나 섹션이 빠지면 PR 생성 금지.
4. 즉시 `gh pr create` 실행. 사용자 승인 요청 금지 — 승인 게이트는 호출자 스킬의 Phase 2/7 정책만 따른다.
5. PR 생성 후 메타데이터 설정:
   - **Assignee**: `gh pr edit {PR_NUMBER} --add-assignee @me`
   - **Label**: 변경 내용의 성격에 맞는 label을 선택하여 적용
     ```bash
     gh label list --limit 50  # 사용 가능한 label 확인
     gh pr edit {PR_NUMBER} --add-label "{LABELS}"
     ```

PR 대상: $ARGUMENTS
