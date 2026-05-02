---
name: commit
description: Spakky Framework 커밋 메시지를 Conventional Commits 형식으로 작성합니다
argument-hint: "[추가 설명]"
user-invocable: true
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
| `tracing` | `core/spakky-tracing` |
| `logging` | `plugins/spakky-logging` |
| `fastapi` | `plugins/spakky-fastapi` |
| `kafka` | `plugins/spakky-kafka` |
| `rabbitmq` | `plugins/spakky-rabbitmq` |
| `security` | `plugins/spakky-security` |
| `sqlalchemy` | `plugins/spakky-sqlalchemy` |
| `typer` | `plugins/spakky-typer` |
| `celery` | `plugins/spakky-celery` |

여러 패키지 변경 시 핵심 변경의 scope 사용, 또는 scope 생략.

## 워크플로우

1. 변경된 패키지 디렉토리에서 `uv run ruff format .` 선행 (pre-commit hook 실패 방지)
2. `git diff --cached`로 스테이지된 변경 확인
3. 변경 내용 분석 후 적절한 type, scope, subject 결정
4. 커밋 메시지를 결정하고 **자동 커밋** 실행 (사용자 승인 불필요)

$ARGUMENTS
