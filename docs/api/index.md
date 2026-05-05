# API 레퍼런스

이 섹션은 Spakky Framework의 모든 패키지에 대한 API 문서를 자동 생성하여 제공합니다.

소스 코드의 docstring을 기반으로 작성되며, 각 클래스·함수·데코레이터의 시그니처와 사용법을 확인할 수 있습니다.

## 코어

- [spakky](core/spakky.md) — DI 컨테이너, AOP, 부트스트랩
- [spakky-domain](core/spakky-domain.md) — DDD 빌딩 블록
- [spakky-data](core/spakky-data.md) — Repository, Transaction 추상화
- [spakky-event](core/spakky-event.md) — 인프로세스 이벤트
- [spakky-task](core/spakky-task.md) — 태스크 추상화
- [spakky-agent](core/spakky-agent.md) — Agentic workflow core 계약
- [spakky-tracing](core/spakky-tracing.md) — 분산 트레이싱 추상화
- [spakky-outbox](core/spakky-outbox.md) — Outbox 패턴
- [spakky-saga](core/spakky-saga.md) — 사가 오케스트레이션
- [spakky-actuator](core/spakky-actuator.md) — Actuator 상태/정보 계약
- [spakky-cache](core/spakky-cache.md) — 애플리케이션 데이터 캐시 계약과 AOP 어노테이션

## 플러그인

- [spakky-logging](plugins/spakky-logging.md) — 구조화된 로깅
- [spakky-fastapi](plugins/spakky-fastapi.md) — FastAPI 통합
- [spakky-rabbitmq](plugins/spakky-rabbitmq.md) — RabbitMQ 통합
- [spakky-security](plugins/spakky-security.md) — 보안 (JWT, 인증)
- [spakky-typer](plugins/spakky-typer.md) — Typer CLI 통합
- [spakky-kafka](plugins/spakky-kafka.md) — Kafka 통합
- [spakky-sqlalchemy](plugins/spakky-sqlalchemy.md) — SQLAlchemy 통합
- [spakky-celery](plugins/spakky-celery.md) — Celery 통합
- [spakky-opentelemetry](plugins/spakky-opentelemetry.md) — OpenTelemetry 브릿지
- [spakky-grpc](plugins/spakky-grpc.md) — gRPC 통합
- [spakky-redis](plugins/spakky-redis.md) — Redis 캐시 백엔드
- [spakky-vllm](plugins/spakky-vllm.md) — vLLM 모델 adapter
