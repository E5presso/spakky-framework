# API Reference

이 섹션은 Spakky Framework의 모든 패키지에 대한 API 문서를 자동 생성하여 제공합니다.

소스 코드의 docstring을 기반으로 작성되며, 각 클래스·함수·데코레이터의 시그니처와 사용법을 확인할 수 있습니다.

## Core

- [spakky](core/spakky.md) — DI Container, AOP, 부트스트랩
- [spakky-domain](core/spakky-domain.md) — DDD 빌딩 블록
- [spakky-data](core/spakky-data.md) — Repository, Transaction 추상화
- [spakky-event](core/spakky-event.md) — 인프로세스 이벤트
- [spakky-task](core/spakky-task.md) — 태스크 추상화
- [spakky-outbox](core/spakky-outbox.md) — Outbox 패턴

## Plugins

- [spakky-logging](plugins/spakky-logging.md) — 구조화된 로깅
- [spakky-fastapi](plugins/spakky-fastapi.md) — FastAPI 통합
- [spakky-rabbitmq](plugins/spakky-rabbitmq.md) — RabbitMQ 통합
- [spakky-security](plugins/spakky-security.md) — 보안 (JWT, 인증)
- [spakky-typer](plugins/spakky-typer.md) — Typer CLI 통합
- [spakky-kafka](plugins/spakky-kafka.md) — Kafka 통합
- [spakky-sqlalchemy](plugins/spakky-sqlalchemy.md) — SQLAlchemy 통합
- [spakky-celery](plugins/spakky-celery.md) — Celery 통합
