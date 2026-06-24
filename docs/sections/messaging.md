# 메시징과 워크플로우

> 비동기 태스크, 메시지 브로커, 분산 트랜잭션 — 서비스 사이의 메시지 흐름과 장기 워크플로우를 다룹니다.

이벤트를 외부로 내보내거나, 여러 서비스에 걸친 트랜잭션을 조율해야 할 때 이 채널을 봅니다.

## 기초

| 문서 | 무엇을 배우나요 |
| --- | --- |
| [Celery 태스크](../guides/celery.md) | Celery worker로 백그라운드 태스크 실행하기 |
| [RabbitMQ 통합](../guides/rabbitmq.md) | RabbitMQ로 이벤트 주고받기 |
| [Kafka 통합](../guides/kafka.md) | Kafka로 이벤트 스트리밍하기 |
| [Transactional Outbox](../guides/outbox.md) | 이벤트 발행과 DB 트랜잭션을 원자적으로 묶기 |
| [사가 오케스트레이션](../guides/saga.md) | 분산 트랜잭션을 보상 단계로 조율하기 |

## 심화

| 문서 | 무엇을 배우나요 |
| --- | --- |
| [사가 심화](../guides/saga-advanced.md) | 보상 설계, 상태 전이, 실패 복구 |
