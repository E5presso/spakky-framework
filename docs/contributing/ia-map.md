# 정보구조(IA) 지도

> Spakky 사용자 문서의 정보구조 골격입니다. 후속 문서 작업은 이 지도가 정한 채널·기초/심화 위치를 따릅니다. 새 페이지를 추가할 때 "이 페이지가 어느 채널의 기초인가 심화인가"를 먼저 정한 뒤 nav에 배치합니다.

## 골격 원칙

- **채널/기능 축**: nav는 사용자가 만들려는 것(핵심·경계·메시징·보안·운영·Agent)을 기준으로 나뉩니다.
- **기초/심화 2단**: 각 채널은 *기초*(입문 가이드)와 *심화*(설계·내부·확장)로 나뉩니다.
- **채널 랜딩 페이지**: 각 채널은 진입점 페이지(`sections/<채널>.md`)를 가지며, 그 채널의 기초/심화 문서를 표로 안내합니다.
- **도식 표준**: 모든 도식은 [도식(Mermaid) 사용 표준](diagram-standard.md)을 따릅니다.

## 채널 구성

| 채널 | 랜딩 페이지 | 기초 | 심화 |
| --- | --- | --- | --- |
| 핵심 (Core) | `sections/core.md` | DI & Pod, AOP, 도메인 모델링, 이벤트 시스템, 태스크 & 스케줄링 | DI/IoC 컨테이너, DI & Pod 심화, AOP 가이드, 이벤트 시스템(심화) |
| 애플리케이션 경계 | `sections/boundaries.md` | FastAPI, CLI(Typer), gRPC, 데이터베이스(SQLAlchemy) | gRPC 심화 |
| 메시징과 워크플로우 | `sections/messaging.md` | Celery, RabbitMQ, Kafka, Outbox, 사가 | 사가 심화 |
| 보안 | `sections/security.md` | 보안 | 보안 심화, 인증/인가 전환, 마일스톤 스펙 |
| 운영 | `sections/operations.md` | 로깅, 트레이싱, OpenTelemetry, Actuator, 캐시 | — |
| Agent | `sections/agent.md` | AI Agent 개발, LLM 모델 라우팅, CodeAssistant 예제 | AI Agent 심화 (+ 프로토콜 어댑터: AG-UI·A2A·MCP) |

## 기존 페이지의 새 위치 (이동 계획)

기존 문서 파일은 mkdocstrings·기존 링크 호환을 위해 **현재 경로를 그대로 유지**하고, nav 위계만 채널/기능 축 + 기초/심화로 재편했습니다. 아래는 각 페이지가 새 nav에서 차지하는 위치입니다.

| 페이지 파일 | 이전 nav 위치 | 새 nav 위치 |
| --- | --- | --- |
| `guides/dependency-injection.md` | 가이드 > 시작하기 | 핵심 > 기초 |
| `guides/aop.md` | 가이드 > 시작하기 | 핵심 > 기초 |
| `guides/domain-modeling.md` | 가이드 > 시작하기 | 핵심 > 기초 |
| `guides/events.md` | 가이드 > 시작하기 | 핵심 > 기초 |
| `guides/tasks.md` | 가이드 > 시작하기 | 핵심 > 기초 |
| `di-container.md` | 심화 가이드 | 핵심 > 심화 |
| `guides/dependency-injection-advanced.md` | 심화 가이드 | 핵심 > 심화 |
| `aop-guide.md` | 심화 가이드 | 핵심 > 심화 |
| `event-system.md` | 심화 가이드 | 핵심 > 심화 |
| `guides/fastapi.md` | 가이드 > 애플리케이션 경계 | 애플리케이션 경계 > 기초 |
| `guides/typer.md` | 가이드 > 애플리케이션 경계 | 애플리케이션 경계 > 기초 |
| `guides/grpc.md` | 가이드 > 애플리케이션 경계 | 애플리케이션 경계 > 기초 |
| `guides/sqlalchemy.md` | 가이드 > 애플리케이션 경계 | 애플리케이션 경계 > 기초 |
| `guides/grpc-advanced.md` | 심화 가이드 | 애플리케이션 경계 > 심화 |
| `guides/celery.md` | 가이드 > 메시징과 워크플로우 | 메시징과 워크플로우 > 기초 |
| `guides/rabbitmq.md` | 가이드 > 메시징과 워크플로우 | 메시징과 워크플로우 > 기초 |
| `guides/kafka.md` | 가이드 > 메시징과 워크플로우 | 메시징과 워크플로우 > 기초 |
| `guides/outbox.md` | 가이드 > 메시징과 워크플로우 | 메시징과 워크플로우 > 기초 |
| `guides/saga.md` | 가이드 > 메시징과 워크플로우 | 메시징과 워크플로우 > 기초 |
| `guides/saga-advanced.md` | 심화 가이드 | 메시징과 워크플로우 > 심화 |
| `guides/security.md` | 가이드 > 운영 | 보안 > 기초 |
| `guides/security-advanced.md` | 심화 가이드 | 보안 > 심화 |
| `guides/auth-migration.md` | 심화 가이드 | 보안 > 심화 |
| `planning/auth-authorization-milestone-scope.md` | 심화 가이드 | 보안 > 심화 |
| `guides/logging.md` | 가이드 > 운영 | 운영 > 기초 |
| `guides/tracing.md` | 가이드 > 운영 | 운영 > 기초 |
| `guides/opentelemetry.md` | 가이드 > 운영 | 운영 > 기초 |
| `guides/actuator.md` | 가이드 > 운영 | 운영 > 기초 |
| `guides/cache.md` | 가이드 > 운영 | 운영 > 기초 |
| `guides/agents.md` | 가이드 > Agent | Agent > 기초 |
| `guides/llm-routing.md` | 신규 | Agent > 기초 |
| `guides/agent-code-assistant.md` | 가이드 > Agent | Agent > 기초 |
| `guides/agents-advanced.md` | 심화 가이드 | Agent > 심화 |
| `plugin-api.md` | 심화 가이드 | 참조 |

## 신규 스캐폴딩 페이지

| 페이지 파일 | 채널 위치 | 상태 |
| --- | --- | --- |
| `sections/core.md` | 핵심 랜딩 | 작성 완료 |
| `sections/boundaries.md` | 애플리케이션 경계 랜딩 | 작성 완료 |
| `sections/messaging.md` | 메시징과 워크플로우 랜딩 | 작성 완료 |
| `sections/security.md` | 보안 랜딩 | 작성 완료 |
| `sections/operations.md` | 운영 랜딩 | 작성 완료 |
| `sections/agent.md` | Agent 랜딩 | 작성 완료 |
| `contributing/diagram-standard.md` | 기여 | 작성 완료 |
| `contributing/ia-map.md` | 기여 | 작성 완료 (이 문서) |
| `guides/agent-ag-ui.md` | Agent > 프로토콜 어댑터 | 작성 완료 |
| `guides/agent-a2a.md` | Agent > 프로토콜 어댑터 | 작성 완료 |
| `guides/agent-mcp.md` | Agent > 프로토콜 어댑터 | 작성 완료 |
| `guides/llm-routing.md` | Agent > 기초 | 작성 완료 |
