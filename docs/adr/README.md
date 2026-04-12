# Architecture Decision Records (ADR)

이 디렉토리는 Spakky Framework의 주요 아키텍처 의사결정을 기록합니다.

## ADR이란?

Architecture Decision Record는 소프트웨어 아키텍처에 영향을 미치는 **주요 설계 결정**을 구조화된 형식으로 기록한 문서입니다.
각 ADR은 결정의 맥락, 고려한 대안, 최종 선택과 그 근거를 포함합니다.

## 상태 정의

| 상태           | 의미                               |
| -------------- | ---------------------------------- |
| **Proposed**   | 제안됨 — 검토 및 논의 필요         |
| **Accepted**   | 채택됨 — 구현 진행                 |
| **Superseded** | 대체됨 — 새 ADR로 교체 (링크 포함) |
| **Deprecated** | 폐기됨 — 더 이상 유효하지 않음     |

## ADR 목록

| #                                         | 제목                                                      | 상태     | 날짜       |
| ----------------------------------------- | --------------------------------------------------------- | -------- | ---------- |
| [ADR-0001](0001-event-system-redesign.md) | 이벤트 시스템 재설계 — 단일 진입점, EventBus/EventTransport 분리, Outbox Seam | Accepted | 2026-03-06 |
| [ADR-0002](0002-outbox-plugin-architecture.md) | Outbox 플러그인 아키텍처 — 추상화와 구현체 분리 | Accepted | 2026-03-10 |
| [ADR-0003](0003-task-schedule-decorator-split.md) | @task / @schedule 데코레이터 분리 — 온디맨드 디스패치와 정기 실행 분리 | Accepted | 2026-03-15 |
| [ADR-0004](0004-distributed-tracing-architecture.md) | 분산 트레이싱 아키텍처 — `spakky-tracing` 코어 + OTel 플러그인 분리 | Accepted | 2026-03-15 |
| [ADR-0005](0005-merge-outbox-sqlalchemy-into-sqlalchemy.md) | Outbox SQLAlchemy 구현체를 spakky-sqlalchemy에 통합 | Accepted | 2026-03-15 |
| [ADR-0006](0006-move-outbox-to-core.md) | spakky-outbox를 core 패키지로 승격 | Accepted | 2026-03-15 |
| [ADR-0007](0007-spakky-saga-plan.md) | spakky-saga — 분산 트랜잭션 사가 오케스트레이션 코어 패키지 | Proposed | 2026-04-05 |
| [ADR-0008](0008-type-safety-hardening.md) | 타입 안전성 강화 — pyrefly ignore 박멸과 구조적 개선 | Accepted | 2026-04-13 |

## 새 ADR 작성 가이드

1. 다음 번호로 파일 생성: `NNNN-<slug>.md`
2. [ADR 템플릿](TEMPLATE.md)을 복사하여 작성
3. 위 목록에 항목 추가
4. PR 또는 커밋으로 제출
