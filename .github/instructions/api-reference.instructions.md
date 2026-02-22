---
applyTo: "**/*.py"
---

# Spakky Framework API Reference

이 문서는 Python 코드 작성 시 자동 적용됩니다.

## Core API

| Decorator / Class | Import Path | Purpose |
|---|---|---|
| `@Pod(name=, scope=)` | `spakky.core.pod.annotations.pod` | Register class/function as managed bean |
| `@Primary` | `spakky.core.pod.annotations.primary` | Mark preferred implementation |
| `@Order(n)` | `spakky.core.pod.annotations.order` | Control execution order |
| `Tag` | `spakky.core.pod.annotations.tag` | Base class for custom metadata tags |
| `ITagRegistry` | `spakky.core.pod.interfaces.tag_registry` | Tag registry interface (register, query tags) |
| `ITagRegistryAware` | `spakky.core.pod.interfaces.aware.tag_registry_aware` | Aware interface for tag registry injection |
| `@Aspect()` / `@AsyncAspect()` | `spakky.core.aop.aspect` | Sync/Async aspect decorator |
| `IAsyncAspect` / `IAspect` | `spakky.core.aop.interfaces.aspect` | Aspect interfaces |
| `@Before` / `@After` / `@Around` / `@AfterReturning` / `@AfterRaising` | `spakky.core.aop.pointcut` | AOP pointcut decorators |
| `@Logging()` | `spakky.core.aspects.logging` | Built-in logging annotation |
| `@Controller` | `spakky.core.stereotype.controller` | Base controller stereotype |
| `@UseCase` | `spakky.core.stereotype.usecase` | Business logic stereotype |
| `SpakkyApplication` | `spakky.core.application.application` | App builder (`.load_plugins()` → `.add()` → `.scan()` → `.start()`) |
| `ApplicationContext` | `spakky.core.application.application_context` | IoC container context (implements IContainer, ITagRegistry) |

## Plugin API

| Decorator / Class | Import Path | Purpose |
|---|---|---|
| `@ApiController(prefix)` | `spakky.plugins.fastapi.stereotypes.api_controller` | FastAPI REST controller |
| `@CliController(group)` | `spakky.plugins.typer.stereotypes.cli_controller` | Typer CLI controller |
| `@EventHandler` / `@on_event` | `spakky.event.stereotype.event_handler` | Event handler stereotype |

## Pod Scopes

- `SINGLETON` (default): 컨테이너당 하나의 인스턴스
- `PROTOTYPE`: 요청마다 새 인스턴스
- `CONTEXT`: 요청/컨텍스트 수명주기에 따른 인스턴스
