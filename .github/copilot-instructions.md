# Spakky Framework - AI Coding Instructions

> **컨텍스트 로딩 (필요 시)**:
> - 코딩 스타일/네이밍 참조 → [CONTRIBUTING.md](../CONTRIBUTING.md)
> - 아키텍처/이벤트 시스템 작업 → [ARCHITECTURE.md](../ARCHITECTURE.md)
> - API 사용 예제 필요 → [README.md](../README.md)

## 커스터마이징 구조

| Layer | 위치 | 역할 |
|-------|------|------|
| Custom Agent | `.github/agents/spakky-dev.agent.md` | 도구 제한, 행동 규칙 |
| File Instructions | `.github/instructions/*.instructions.md` | 파일 패턴별 자동 적용 규칙 |
| Prompt Files | `.github/prompts/*.prompt.md` | 반복 작업 워크플로우 |

하네스 변경 시 → [harness-update.prompt.md](./prompts/harness-update.prompt.md) 참조

## Overview

Spring-inspired DI/IoC framework for Python 3.11+ with AOP and plugin system. Uses `uv` workspace monorepo.

- **Core** (`core/`): `spakky`, `spakky-domain`, `spakky-data`, `spakky-event`
- **Plugins** (`plugins/`): `spakky-fastapi`, `spakky-rabbitmq`, `spakky-kafka`, `spakky-security`, `spakky-typer`, `spakky-sqlalchemy`

**API Reference**: `.github/instructions/api-reference.instructions.md` (Python 파일 작성 시 자동 적용)

## Monorepo Rules

```bash
uv sync --all-packages --all-extras  # Root: install all
uv sync --all-extras                 # Sub-package: install only that package
```

## AI Agent Rules

### Tool Usage

1. **Prefer integrated tools** (`execute/runTests`, `get_errors`, `read_file`, etc.) over terminal commands
2. **Always prefix** Python commands with `uv run` (venv is NOT activated in PTY)
3. **NEVER use multiline quoted commands** in terminal (heredocs, `python -c "..."`) — PTY will hang
4. **Use file tools** (`create_file`, `replace_string_in_file`) instead of `cat`/`echo` redirections
5. **Verify terminal commands** by executing them before documenting

### MCP Write Operations

**CRITICAL**: Before invoking any MCP tool that performs write operations (e.g., `mcp_github_create_pull_request`, `mcp_github_add_issue_comment`, `mcp_github_create_or_update_file`), you MUST:

1. **Output the full content** in markdown format for user review
2. **Wait for explicit approval** before executing the tool call
3. This applies to: PR creation, issue creation/updates, file creation/updates, comments, reviews, etc.

### Documentation Maintenance Rules

**This section MUST be preserved in all future versions.**

1. **Code-first**: Every statement must be backed by actual code. No hallucinations.
2. **Cross-reference**: Find the exact code line before documenting any feature.
3. **Sync all docs**: Changes to codebase → update all relevant markdown files (NOT `CHANGELOG.md`, it's auto-generated).
4. **Sub-package READMEs**: Always check/update READMEs in all `core/*/README.md` and `plugins/*/README.md`.
5. **Priority**: Code > `CONTRIBUTING.md` > this file > `README.md`. If docs contradict code, update docs.
6. **Verification checklist**: File paths, class/function names, method signatures, import paths, env var prefixes — all must be verified against actual code.
