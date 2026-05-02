---
name: create-pr
description: Spakky Framework PR을 생성합니다
argument-hint: "[PR 설명]"
user-invocable: false
---

# PR 생성

1. `git diff develop...HEAD`로 변경 파일 확인
2. Conventional Commits 형식 타이틀 (scope는 `/commit` 스킬 참조)
   - **타이틀에 closes 대상 이슈 번호를 포함한다.** 예: `feat(rabbitmq): add dead letter queue support (#42)`
   - 이슈 번호는 커밋 메시지의 `(#N)` 또는 브랜치명(`feat/42` 등)에서 추출한다.
3. PR 내용을 마크다운으로 출력 → **사용자 승인 후** `gh pr create` 실행
4. PR 생성 후 메타데이터 설정:
   - **Assignee**: `gh pr edit {PR_NUMBER} --add-assignee @me`
   - **Label**: 변경 내용의 성격에 맞는 label을 선택하여 적용
     ```bash
     gh label list --limit 50  # 사용 가능한 label 확인
     gh pr edit {PR_NUMBER} --add-label "{LABELS}"
     ```

PR 대상: $ARGUMENTS
