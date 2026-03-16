---
name: commit
description: Spakky Framework 커밋 메시지 작성
tools:
  - search/changes
  - execute/runInTerminal
---

# 커밋 메시지 작성

Conventional Commits 형식: `<type>(<scope>): <subject>`

**Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

| Scope | 패키지 경로 |
|-------|------------|
| `core` | `core/spakky` |
| `domain` | `core/spakky-domain` |
| `data` | `core/spakky-data` |
| `event` | `core/spakky-event` |
| `task` | `core/spakky-task` |
| `outbox` | `core/spakky-outbox` |
| `logging` | `plugins/spakky-logging` |
| `fastapi` | `plugins/spakky-fastapi` |
| `kafka` | `plugins/spakky-kafka` |
| `rabbitmq` | `plugins/spakky-rabbitmq` |
| `security` | `plugins/spakky-security` |
| `sqlalchemy` | `plugins/spakky-sqlalchemy` |
| `typer` | `plugins/spakky-typer` |
| `celery` | `plugins/spakky-celery` |

여러 패키지 변경 시 핵심 변경의 scope 사용, 또는 scope 생략.
