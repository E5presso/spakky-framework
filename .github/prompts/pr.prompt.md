---
name: pr
description: Spakky Framework PR 생성 워크플로우
agent: spakky-dev
tools:
  - read/readFile
  - search
  - search/listDirectory
  - search/changes
  - github/*
  - execute/runInTerminal
  - execute/getTerminalOutput
  - search/usages
  - todo
  - web/fetch
---

# PR 생성 워크플로우

## Step 1: 변경 사항 확인

1. `git diff develop` 또는 `get_changed_files`로 변경 파일 목록을 확인하세요.
2. 각 변경 파일의 목적을 정리하세요.

## Step 2: PR 템플릿 확인

[PULL_REQUEST_TEMPLATE.md](../../.github/PULL_REQUEST_TEMPLATE.md)를 읽고 형식을 따르세요.

## Step 3: PR 내용 작성

1. **Title**: Conventional Commits 형식 (`feat(<scope>): <subject>`)
2. **Description**: 변경 사항의 목적과 구현 내용
3. **Related Issue**: `Fixes #<number>` 또는 `Closes #<number>`
4. **Type of Change**: 적절한 항목 체크
5. **Checklist**: 모든 항목 확인

### Scope 규칙

| Scope | 패키지 |
|-------|--------|
| `core` | `core/spakky` |
| `domain` | `core/spakky-domain` |
| `data` | `core/spakky-data` |
| `event` | `core/spakky-event` |
| `fastapi` | `plugins/spakky-fastapi` |
| `kafka` | `plugins/spakky-kafka` |
| `rabbitmq` | `plugins/spakky-rabbitmq` |
| `security` | `plugins/spakky-security` |
| `typer` | `plugins/spakky-typer` |
| `plugin.sqlalchemy` | `plugins/spakky-sqlalchemy` |

## Step 4: 사용자 승인

**PR 작성 내용을 마크다운으로 전체 출력하고, 사용자 승인을 받은 후에만 MCP 도구를 호출하세요.**

PR 대상: ${input:description:PR에 대해 설명하세요}
