# OpenTelemetry 통합

> Spakky tracing 추상화와 privacy-safe Agent telemetry를 OpenTelemetry SDK에 연결하는 방법을 설명합니다.

`spakky-opentelemetry`는 Spakky의 분산 트레이싱 추상화(`spakky-tracing`)와 core
`IAgentTelemetry`를 OpenTelemetry SDK에 연결하는 브릿지 플러그인입니다.

---

## spakky-tracing과의 관계

Spakky의 트레이싱 아키텍처는 두 계층으로 나뉩니다:

| 패키지 | 역할 |
|--------|------|
| `spakky-tracing` (Core) | `TraceContext`, `ITracePropagator` 추상화, `W3CTracePropagator` 기본 구현 |
| `spakky-opentelemetry` (Plugin) | SDK provider/exporter, propagator 교체, Agent telemetry binding |

`spakky-tracing`만 사용하면 외부 의존성 없이 W3C traceparent 전파가 동작합니다.
`spakky-opentelemetry`를 추가하면 OTLP exporter를 통해 Jaeger, Tempo 등 외부 백엔드로 트레이스를 전송할 수 있습니다.

> 트레이싱 기본 개념과 `TraceContext` API는 [분산 트레이싱 가이드](tracing.md)를 참고하세요.

---

## 플러그인 활성화

```python
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
import spakky.tracing
import spakky.plugins.opentelemetry
import apps

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

선택적 `include`를 사용할 때 propagator 교체까지 활성화하려면 `spakky.tracing.PLUGIN_NAME`도 함께 포함해야 합니다. `spakky-tracing`이 기본 `W3CTracePropagator`를 등록하고, `spakky-opentelemetry`의 엔트리포인트(`spakky.plugins.opentelemetry.main:initialize`)가 다음 Pod를 등록합니다:

1. **`OpenTelemetryConfig`** --- 환경변수 기반 설정 (`@Configuration`)
2. **`OTelSetupPostProcessor`** --- `TracerProvider` 초기화 및 propagator 교체 (`IPostProcessor`)
3. **`LogContextBridge`** --- `spakky-logging`이 있을 때 trace context를 log context로 동기화
4. **`OpenTelemetryAgentTelemetry`** --- `IAgentTelemetry`에 자동 bind되는 Agent span sink

---

## Agent telemetry binding

플러그인의 `initialize()`는 `OpenTelemetryAgentTelemetry`를 Pod로 등록하고
`IAgentTelemetry -> OpenTelemetryAgentTelemetry` binding을 추가합니다. 따라서
`spakky-agent`도 로드한 application에서 `IAgentRunnerFactory`를 생성자 주입받아 여는 표준
adapter 경로는 별도 sink 조립 없이 이 binding을 사용합니다. Direct `AgentRunner`는
`with_telemetry()`를 사용하고, synthesized
`agent.execute()` 경로에서 직접 관측하려면 Agent constructor에 `IAgentTelemetry`를
주입합니다.

Core가 보내는 operation mapping은 고정되어 있습니다.

| `AgentSpanKind` | `gen_ai.operation.name` | OTel `SpanKind` |
| --- | --- | --- |
| `RUN` | `invoke_agent` | `INTERNAL` |
| `MODEL` | `generate_content` | `CLIENT` |
| `TOOL` | `execute_tool` | `INTERNAL` |
| `RETRIEVAL` | `retrieval` | `CLIENT` |

`AgentSpanRecord.started_at_ns`와 `ended_at_ns`는 OTel span에 exact nanosecond time으로
전달됩니다. Ambient Spakky `TraceContext`가 있으면 `OTelContextConverter`가 non-recording
parent span으로 변환해 같은 trace/span parent를 보존합니다. Spakky context가 없으면
ambient OTel span을 추측하지 않고 root span을 만듭니다. Core `OK`/`ERROR` status는 OTel
status로, error code는 `error.type`과 status description으로 매핑됩니다.

Attributes는 scalar만 허용됩니다. Adapter는 caller가 넣어도 다음 raw body를 exporter로
보내지 않습니다.

- prompt, context, system instructions, input/output messages와 completion
- retrieval query와 retrieved content
- tool arguments와 tool result
- caller가 덮어쓰려는 `gen_ai.operation.name`과 `error.type`

남는 값은 agent/run ID, operation kind, route, usage/cost, tool identity, retrieval count와
fixed scope 같은 correlation metadata입니다. Telemetry sink가 실패하면 runner는 untyped
backend exception 대신 `AgentTelemetryError`를 raise합니다. Core 실행·cost와 함께 쓰는
방법은 [Agent Memory, Evaluation, Cost와 Telemetry](agent-operations.md)를 확인하세요.

이 binding은 새로운 network export 경로를 따로 만들지 않습니다. 아래
`OpenTelemetryConfig`의 OTLP/console/none과 기존 endpoint/sample rate가 모든 span export를
계속 소유합니다.

---

## 설정

`OpenTelemetryConfig`는 `@Configuration`이므로 환경변수에서 자동 로딩됩니다.

```python
from spakky.plugins.opentelemetry.config import OpenTelemetryConfig, ExporterType
```

| 환경변수 | 필드 | 타입 / 기본값 | 설명 |
|----------|------|---------------|------|
| `SPAKKY_OTEL_SERVICE_NAME` | `service_name` | `str` / `"spakky-service"` | OTel 리소스의 `service.name` |
| `SPAKKY_OTEL_EXPORTER_TYPE` | `exporter_type` | `ExporterType` / `OTLP` | span exporter 유형 |
| `SPAKKY_OTEL_EXPORTER_ENDPOINT` | `exporter_endpoint` | `str` / `"http://localhost:4317"` | OTLP collector gRPC 엔드포인트 |
| `SPAKKY_OTEL_SAMPLE_RATE` | `sample_rate` | `float` / `1.0` | 0.0~1.0 sampling rate |

### ExporterType

```python
from spakky.plugins.opentelemetry.config import ExporterType


exporter_values = tuple(option.value for option in ExporterType)
assert exporter_values == ("otlp", "console", "none")
```

---

## W3CTracePropagator 자동 교체

플러그인을 활성화하면 **애플리케이션 코드 변경 없이** propagator가 교체됩니다.

`OTelSetupPostProcessor`는 `IPostProcessor`를 구현하며, 컨테이너의 모든 Pod를 순회합니다.
`W3CTracePropagator` 인스턴스를 발견하면 `OTelTracePropagator`로 교체합니다:

```python
# post_processor.py 핵심 로직 (참고용)
def post_process(self, pod: object) -> object:
    if not self.__configured:
        self.__configured = True
        self._configure_tracer_provider()
    if isinstance(pod, W3CTracePropagator):
        return OTelTracePropagator()
    return pod
```

이 교체 과정에서 `_configure_tracer_provider()`가 한 번만 실행되어 `TracerProvider`를 전역으로 설정합니다:

1. `OpenTelemetryConfig`에서 설정을 읽음
2. `Resource`에 `service.name` 설정
3. `TraceIdRatioBased` sampler로 샘플링 비율 적용
4. `ExporterType`에 따라 `BatchSpanProcessor`에 exporter 연결
5. `trace.set_tracer_provider(provider)` 호출

### OTelTracePropagator

`OTelTracePropagator`는 `ITracePropagator`를 구현하며, Spakky의 `TraceContext`와 OpenTelemetry의 `Context` 사이를 변환합니다:

```python
from spakky.plugins.opentelemetry.propagator import OTelTracePropagator
```

- **`inject(carrier)`**: `TraceContext.get()`으로 현재 컨텍스트를 읽어 OTel `Context`로 변환 후, W3C `TraceContextTextMapPropagator`로 헤더 직렬화
- **`extract(carrier)`**: OTel propagator로 헤더를 파싱하여 `SpanContext`를 추출 후, `TraceContext`로 역변환
- **`fields()`**: `["traceparent", "tracestate"]` 반환

기존에 `W3CTracePropagator`에 의존하던 코드(FastAPI 미들웨어, RabbitMQ/Kafka 어댑터 등)는 `ITracePropagator` 인터페이스를 통해 주입받으므로, propagator 교체가 투명하게 이루어집니다.

---

## LogContextBridge --- 트레이스-로깅 동기화

`spakky-logging`이 설치되어 있으면, `LogContextBridge` pod instance의 `sync()`를 호출하여 현재 `TraceContext`의 trace_id/span_id를 `LogContext`에 바인딩할 수 있습니다.

```python
from spakky.plugins.opentelemetry.bridge import LogContextBridge
```

### 사용 시나리오

미들웨어나 Aspect에서 `TraceContext`를 설정한 직후 호출합니다:

```python
from spakky.tracing.context import TraceContext
from spakky.plugins.opentelemetry.bridge import LogContextBridge

# 인바운드 요청에서 trace 복원 후
ctx = propagator.extract(headers)
if ctx is not None:
    TraceContext.set(ctx.child())

# 로그 컨텍스트에 trace_id/span_id 동기화
bridge = app.container.get(type_=LogContextBridge)
bridge.sync()
# → LogContext.bind(trace_id=ctx.trace_id, span_id=ctx.span_id)
```

### 동작 조건

`LogContextBridge`는 생성자에서 `ILogContextBinder | None`을 Optional DI로 주입받습니다. `spakky-logging`이 설치되어 `ILogContextBinder` 구현체가 컨테이너에 등록되어 있으면 자동으로 주입되고, 없으면 `None`이 주입됩니다.

| 조건 | 동작 |
|------|------|
| `ILogContextBinder`가 `None` (spakky-logging 미등록) | `sync()`는 no-op |
| `TraceContext.get()`이 `None` | `LogContext.unbind("trace_id", "span_id")` 호출 |
| `TraceContext`가 활성 상태 | `LogContext.bind(trace_id=..., span_id=...)` 호출 |

`spakky-logging`은 선택적 의존성입니다. 설치하려면:

```bash
uv add "spakky-opentelemetry[logging]"
```

---

## OTLP Exporter 설정 예제

### Jaeger (OTLP gRPC)

```bash
export SPAKKY_OTEL_SERVICE_NAME=order-service
export SPAKKY_OTEL_EXPORTER_TYPE=otlp
export SPAKKY_OTEL_EXPORTER_ENDPOINT=http://jaeger:4317
export SPAKKY_OTEL_SAMPLE_RATE=1.0
```

OTLP exporter는 `spakky-opentelemetry` 기본 dependency에 포함됩니다.

### Grafana Tempo (OTLP gRPC)

```bash
export SPAKKY_OTEL_SERVICE_NAME=order-service
export SPAKKY_OTEL_EXPORTER_TYPE=otlp
export SPAKKY_OTEL_EXPORTER_ENDPOINT=http://tempo:4317
```

### 개발 환경 (콘솔 출력)

```bash
export SPAKKY_OTEL_EXPORTER_TYPE=console
```

### 전파만, 수집 없음

```bash
export SPAKKY_OTEL_EXPORTER_TYPE=none
```

`ExporterType.NONE`을 사용하면 `TracerProvider`가 초기화되지만 exporter가 연결되지 않습니다.
propagator 교체는 그대로 동작하므로, `OTelTracePropagator`를 통한 traceparent 전파는 유지됩니다.

---

## 전체 예제

```python
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
import spakky.tracing
import spakky.plugins.opentelemetry
import apps

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins(include={
        spakky.tracing.PLUGIN_NAME,
        spakky.plugins.opentelemetry.PLUGIN_NAME,
    })
    .scan(apps)
    .start()
)

# spakky-tracing이 W3CTracePropagator를 등록
# spakky-opentelemetry가 이를 OTelTracePropagator로 자동 교체
# → TracerProvider가 OTLP exporter와 함께 초기화
# → 기존 ITracePropagator 의존 코드는 변경 없이 동작
```
