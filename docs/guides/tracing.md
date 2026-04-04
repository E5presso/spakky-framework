# 분산 트레이싱

서비스 간 요청 흐름을 추적하는 분산 트레이싱 시스템입니다.
W3C Trace Context Level 2 표준을 기반으로, 외부 의존성 없이 순수 Python으로 구현됩니다.

---

## 개요

Spakky의 트레이싱은 **애플리케이션 코드 변경 없이** 자동으로 동작합니다.
플러그인을 로드하면 미들웨어와 Aspect가 요청 경계마다 trace를 전파합니다.

```python
# 이것만 하면 됩니다
app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins()  # spakky-fastapi, spakky-rabbitmq 등이 자동으로 트레이싱 연동
    .scan(apps)
    .start()
)

# 비즈니스 로직에는 트레이싱 코드가 없습니다
@UseCase()
class CreateOrderUseCase:
    @transactional
    async def execute(self, command: CreateOrderCommand) -> Order:
        order = Order.create(...)
        return await self._repository.save(order)
        # → HTTP 응답 헤더에 traceparent가 자동 포함
        # → 이벤트 발행 시 traceparent가 메시지 헤더에 자동 주입
```

---

## 핵심 개념

분산 트레이싱에서 하나의 요청은 **Trace**로, 각 처리 단계는 **Span**으로 표현됩니다.

```
[HTTP 요청] trace_id=abc, span_id=001
  │
  ├─→ [Event A] trace_id=abc, span_id=002, parent=001
  │     │
  │     └─→ [Celery Task] trace_id=abc, span_id=003, parent=002
  │
  └─→ [gRPC Call] trace_id=abc, span_id=004, parent=001
```

- **trace_id**: 전체 요청 체인에서 동일하게 유지되는 128-bit 식별자
- **span_id**: 각 처리 단계에서 새로 생성되는 64-bit 식별자
- **parent_span_id**: 부모 span을 가리키는 참조

이 모든 관리는 **프레임워크가 자동으로 처리**합니다. 각 플러그인의 미들웨어/Aspect가:

1. 인바운드 요청에서 `traceparent` 헤더를 추출
2. 없으면 새 root trace를 생성
3. 아웃바운드 요청/이벤트에 `traceparent` 헤더를 자동 주입

---

## 자동 전파가 동작하는 구간

| 바운더리        | 플러그인        | 자동 처리                        |
| --------------- | --------------- | -------------------------------- |
| HTTP 요청/응답  | spakky-fastapi  | 미들웨어가 traceparent 추출/주입 |
| RabbitMQ 메시지 | spakky-rabbitmq | 메시지 헤더에 자동 주입/추출     |
| Kafka 레코드    | spakky-kafka    | 레코드 헤더에 자동 주입/추출     |
| Celery 태스크   | spakky-celery   | 태스크 헤더에 자동 주입/추출     |

> **참고**: 각 플러그인에서 `spakky-tracing`은 optional 의존성입니다. 설치하면 자동으로 활성화됩니다.

---

## 현재 Trace 조회 (선택적)

자동 전파 외에, 비즈니스 로직에서 현재 trace 정보가 필요한 경우에만 직접 조회합니다.
예를 들어 응답 본문에 trace_id를 포함하여 트러블슈팅에 활용할 수 있습니다.

```python
from spakky.tracing.context import TraceContext

@UseCase()
class CreateOrderUseCase:
    @transactional
    async def execute(self, command: CreateOrderCommand) -> CreateOrderResponse:
        order = Order.create(...)
        await self._repository.save(order)

        # 응답에 trace_id 포함 (프로덕션 디버깅용)
        ctx = TraceContext.get()
        return CreateOrderResponse(
            order_id=order.uid,
            trace_id=ctx.trace_id if ctx else None,
        )
```

---

## W3C traceparent 형식

```
00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01
^^  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^  ^^^^^^^^^^^^^^^^  ^^
버전         trace_id (32자)           span_id (16자)  flags
```

- `flags`: `01` = 샘플링됨, `00` = 샘플링 안 됨

---

## 플러그인/프레임워크 개발자를 위한 저수준 API

아래 API는 **새 전송 계층 플러그인을 개발할 때** 사용합니다.
애플리케이션 개발자는 사용할 필요가 없습니다.

### TraceContext 생성

```python
from spakky.tracing.context import TraceContext

# 새 루트 트레이스
ctx = TraceContext.new_root()
TraceContext.set(ctx)

# 자식 span 생성
child = ctx.child()
TraceContext.set(child)
```

### Propagator — 주입/추출

```python
from spakky.tracing.w3c_propagator import W3CTracePropagator

propagator = W3CTracePropagator()

# 아웃바운드: 현재 trace를 헤더에 주입
carrier: dict[str, str] = {}
propagator.inject(carrier)

# 인바운드: 헤더에서 trace 복원
ctx = propagator.extract(carrier)
if ctx is not None:
    TraceContext.set(ctx.child())
```

### contextvars 격리

`TraceContext`는 Python `contextvars`를 사용하므로, `asyncio` 태스크 간에 자동으로 격리됩니다.

```python
import asyncio
from spakky.tracing.context import TraceContext

async def handle_request_a():
    ctx = TraceContext.new_root()
    TraceContext.set(ctx)
    await asyncio.sleep(0)
    assert TraceContext.get() is ctx  # 격리됨

async def handle_request_b():
    assert TraceContext.get() is None  # request_a와 독립

await asyncio.gather(handle_request_a(), handle_request_b())
```

---

## OpenTelemetry 백엔드 통합

기본 `W3CTracePropagator`는 외부 의존성 없이 traceparent 헤더를 직접 직렬화/역직렬화합니다.
프로덕션 환경에서 Jaeger, Tempo 등 외부 백엔드로 트레이스를 전송하려면 `spakky-opentelemetry` 플러그인을 추가합니다.

### 전환 경로: W3CTracePropagator -> OTelTracePropagator

1. `spakky-opentelemetry` 패키지를 설치합니다:

    ```bash
    uv add spakky-opentelemetry "spakky-opentelemetry[otlp]"
    ```

2. 플러그인을 활성화합니다:

    ```python
    import spakky.tracing
    import spakky.plugins.opentelemetry

    app = (
        SpakkyApplication(ApplicationContext())
        .load_plugins(include={
            spakky.tracing.PLUGIN_NAME,
            spakky.plugins.opentelemetry.PLUGIN_NAME,
        })
        .scan(apps)
        .start()
    )
    ```

3. 환경변수로 exporter를 설정합니다:

    ```bash
    export SPAKKY_OTEL_SERVICE_NAME=order-service
    export SPAKKY_OTEL_EXPORTER_TYPE=otlp
    export SPAKKY_OTEL_EXPORTER_ENDPOINT=http://jaeger:4317
    ```

`spakky-opentelemetry`의 `OTelSetupPostProcessor`가 컨테이너 내의 `W3CTracePropagator`를 `OTelTracePropagator`로 자동 교체합니다. `ITracePropagator` 인터페이스를 통해 주입받는 기존 코드는 변경할 필요가 없습니다.

> 설정 상세, ExporterType, LogContextBridge 등은 [OpenTelemetry 통합 가이드](opentelemetry.md)를 참고하세요.
