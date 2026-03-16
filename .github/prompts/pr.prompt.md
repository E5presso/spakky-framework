---
name: pr
description: Spakky Framework PR 생성
agent: spakky-dev
tools:
  - search/changes
  - github/*
  - execute/runInTerminal
---

# PR 생성

1. `git diff develop`로 변경 파일 확인
2. Conventional Commits 형식 타이틀 (scope는 commit 프롬프트 참조)
3. PR 내용을 마크다운으로 출력 → **사용자 승인 후** GitHub MCP 호출

PR 대상: ${input:description:PR에 대해 설명하세요}
