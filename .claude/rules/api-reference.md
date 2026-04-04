---
paths:
  - "**/src/**/*.py"
---

# Spakky Framework API Reference

## Core API

| Decorator / Class | Import Path | Purpose |
|---|---|---|
| `@Pod(name=, scope=)` | `spakky.core.pod.annotations.pod` | Managed bean 등록 |
| `@Primary` | `spakky.core.pod.annotations.primary` | 우선 구현체 지정 |
| `@Order(n)` | `spakky.core.pod.annotations.order` | 실행 순서 제어 |
| `Tag` | `spakky.core.pod.annotations.tag` | 커스텀 메타데이터 태그 베이스 |
| `@Aspect()` / `@AsyncAspect()` | `spakky.core.aop.aspect` | 동기/비동기 Aspect 데코레이터 |
| `IAsyncAspect` / `IAspect` | `spakky.core.aop.interfaces.aspect` | Aspect 인터페이스 |
| `@Before` / `@After` / `@Around` / `@AfterReturning` / `@AfterRaising` | `spakky.core.aop.pointcut` | AOP pointcut 데코레이터 |
| `@Controller` | `spakky.core.stereotype.controller` | 컨트롤러 스테레오타입 |
| `@UseCase` | `spakky.core.stereotype.usecase` | 비즈니스 로직 스테레오타입 |
| `SpakkyApplication` | `spakky.core.application.application` | 앱 빌더 |
| `ApplicationContext` | `spakky.core.application.application_context` | IoC 컨테이너 컨텍스트 |

## Pod Scopes

| Scope | Behavior |
|---|---|
| `SINGLETON` | 컨테이너당 1 인스턴스 (기본값) |
| `PROTOTYPE` | 요청마다 새 인스턴스 |
| `CONTEXT` | 요청/컨텍스트 생명주기당 인스턴스 |

## Logging API (spakky-logging)

| Decorator / Class | Import Path | Purpose |
|---|---|---|
| `@Logging()` | `spakky.plugins.logging` | 메서드 로깅 어노테이션 |
| `LoggingConfig` | `spakky.plugins.logging` | 로깅 설정 (@Configuration) |
| `LogFormat` | `spakky.plugins.logging` | 포맷 열거형 (TEXT, JSON, PRETTY) |
| `LogContext` | `spakky.plugins.logging` | ContextVar 기반 컨텍스트 전파 |

## Data API (spakky-data)

| Decorator / Class | Import Path | Purpose |
|---|---|---|
| `@Repository` | `spakky.data.stereotype.repository` | 데이터 접근 스테레오타입 |
| `@Transactional()` | `spakky.data.aspects.transactional` | 트랜잭션 경계 어노테이션 |
| `IAsyncGenericRepository` | `spakky.data.persistency.repository` | 비동기 제네릭 리포지토리 |
| `AbstractAsyncTransaction` / `AbstractTransaction` | `spakky.data.persistency.transaction` | 트랜잭션 추상화 |

## Event API (spakky-event)

| Decorator / Class | Import Path | Purpose |
|---|---|---|
| `@EventHandler` / `@on_event` | `spakky.event.stereotype.event_handler` | 이벤트 핸들러 + 라우트 |
| `IEventPublisher` / `IAsyncEventPublisher` | `spakky.event.event_publisher` | 이벤트 발행 |
| `IEventBus` / `IAsyncEventBus` | `spakky.event.event_publisher` | 통합 이벤트 전송 |

## Task API (spakky-task)

| Decorator / Class | Import Path | Purpose |
|---|---|---|
| `TaskHandler` | `spakky.task.stereotype.task_handler` | 태스크 핸들러 스테레오타입 |
| `@task` | `spakky.task.stereotype.task_handler` | 디스패치 가능 태스크 데코레이터 |
| `@schedule` | `spakky.task.stereotype.schedule` | 주기적 태스크 스케줄링 데코레이터 |

## Plugin API

| Decorator / Class | Import Path | Purpose |
|---|---|---|
| `@ApiController(prefix)` | `spakky.plugins.fastapi.stereotypes.api_controller` | FastAPI REST 컨트롤러 |
| `@CliController(group)` | `spakky.plugins.typer.stereotypes.cli_controller` | Typer CLI 컨트롤러 |
