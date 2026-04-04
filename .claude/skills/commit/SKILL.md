---
name: commit
description: Spakky Framework 커밋 메시지를 Conventional Commits 형식으로 작성합니다
argument-hint: "[추가 설명]"
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

1. `git diff --cached`로 스테이지된 변경 확인
2. 변경 내용 분석 후 적절한 type, scope, subject 결정
3. 커밋 메시지를 마크다운으로 출력 → **사용자 승인 후** 커밋 실행

$ARGUMENTS
