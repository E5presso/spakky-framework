# Spakky Framework - AI Coding Instructions

> **필수 참조 문서** (세션 시작 시 반드시 읽을 것):
> - [CONTRIBUTING.md](../CONTRIBUTING.md) — 코딩 표준, 에러 클래스 패턴, 네이밍 규칙
> - [README.md](../README.md) — API 사용 예제
> - [ARCHITECTURE.md](../ARCHITECTURE.md) — 이벤트 아키텍처, 시스템 구조

## 커스터마이징 구조

이 프로젝트는 3-Layer AI 커스터마이징을 사용합니다:

| Layer | 위치 | 역할 |
|-------|------|------|
| Custom Agent | `.github/agents/spakky-dev.agent.md` | 도구 제한, 페르소나, 행동 규칙 |
| File Instructions | `.github/instructions/*.instructions.md` | 파일 패턴별 자동 적용 규칙 |
| Prompt Files | `.github/prompts/*.prompt.md` | 반복 작업 워크플로우 (`/implement`, `/test`, `/pr`) |

**전용 에이전트 `spakky-dev`를 사용하면 도구 사용 규칙이 구조적으로 적용됩니다.**

## Overview

Spring-inspired DI/IoC framework for Python 3.11+ with AOP and plugin system. Uses `uv` workspace monorepo.

- **Core** (`core/`): `spakky` (DI/AOP), `spakky-domain` (DDD), `spakky-data` (Repository/Transaction), `spakky-event` (Event handling)
- **Plugins** (`plugins/`): `spakky-fastapi`, `spakky-rabbitmq`, `spakky-kafka`, `spakky-security`, `spakky-typer`, `spakky-sqlalchemy`
- Each package: `src/spakky/...` (source), `tests/` (tests)

## Key API Reference

| Decorator / Class | Import Path | Purpose |
|---|---|---|
| `@Pod(name=, scope=)` | `spakky.core.pod.annotations.pod` | Register class/function as managed bean |
| `@Primary` | `spakky.core.pod.annotations.primary` | Mark preferred implementation |
| `@Order(n)` | `spakky.core.pod.annotations.order` | Control execution order |
| `@Aspect()` / `@AsyncAspect()` | `spakky.core.aop.aspect` | Sync/Async aspect decorator |
| `IAsyncAspect` / `IAspect` | `spakky.core.aop.interfaces.aspect` | Aspect interfaces |
| `@Before` / `@After` / `@Around` / `@AfterReturning` / `@AfterRaising` | `spakky.core.aop.pointcut` | AOP pointcut decorators |
| `@Logging()` | `spakky.core.aspects.logging` | Built-in logging annotation |
| `@Controller` | `spakky.core.stereotype.controller` | Base controller stereotype |
| `@UseCase` | `spakky.core.stereotype.usecase` | Business logic stereotype |
| `@ApiController(prefix)` | `spakky.plugins.fastapi.stereotypes.api_controller` | FastAPI REST controller |
| `@CliController(group)` | `spakky.plugins.typer.stereotypes.cli_controller` | Typer CLI controller |
| `@EventHandler` / `@on_event` | `spakky.event.stereotype.event_handler` | Event handler stereotype |
| `SpakkyApplication` | `spakky.core.application.application` | App builder (`.load_plugins()` → `.add()` → `.scan()` → `.start()`) |
| `ApplicationContext` | `spakky.core.application.application_context` | IoC container context |

**Pod Scopes**: `SINGLETON` (default), `PROTOTYPE`, `CONTEXT`

## Monorepo Rules

### Dependencies

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
