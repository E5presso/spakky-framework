---
name: pr
description: Spakky Framework PR을 생성합니다
argument-hint: "[PR 설명]"
disable-model-invocation: true
---

# PR 생성

1. `git diff main...HEAD`로 변경 파일 확인
2. Conventional Commits 형식 타이틀 (scope는 `/commit` 스킬 참조)
3. PR 내용을 마크다운으로 출력 → **사용자 승인 후** `gh pr create` 실행

PR 대상: $ARGUMENTS
