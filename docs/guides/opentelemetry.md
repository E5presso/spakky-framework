# OpenTelemetry 통합

`spakky-opentelemetry`는 Spakky의 분산 트레이싱 추상화(`spakky-tracing`)를 OpenTelemetry SDK에 연결하는 브릿지 플러그인입니다.

---

## spakky-tracing과의 관계

Spakky의 트레이싱 아키텍처는 두 계층으로 나뉩니다:

| 패키지 | 역할 |
|--------|------|
| `spakky-tracing` (Core) | `TraceContext`, `ITracePropagator` 추상화, `W3CTracePropagator` 기본 구현 |
| `spakky-opentelemetry` (Plugin) | OpenTelemetry SDK `TracerProvider` 초기화, `W3CTracePropagator`를 `OTelTracePropagator`로 자동 교체 |

`spakky-tracing`만 사용하면 외부 의존성 없이 W3C traceparent 전파가 동작합니다.
`spakky-opentelemetry`를 추가하면 OTLP exporter를 통해 Jaeger, Tempo 등 외부 백엔드로 트레이스를 전송할 수 있습니다.

> 트레이싱 기본 개념과 `TraceContext` API는 [분산 트레이싱 가이드](tracing.md)를 참고하세요.

---

## 플러그인 활성화

```python
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
import spakky.plugins.opentelemetry
import apps

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins(include={spakky.plugins.opentelemetry.PLUGIN_NAME})
    .scan(apps)
    .start()
)
```

`load_plugins()`가 `spakky-opentelemetry`의 엔트리포인트(`spakky.plugins.opentelemetry.main:initialize`)를 호출하면, 다음 두 Pod가 컨테이너에 등록됩니다:

1. **`OpenTelemetryConfig`** --- 환경변수 기반 설정 (`@Configuration`)
2. **`OTelSetupPostProcessor`** --- `TracerProvider` 초기화 및 propagator 교체 (`IPostProcessor`)

---

## 설정

`OpenTelemetryConfig`는 `@Configuration`이므로 환경변수에서 자동 로딩됩니다.

```python
from spakky.plugins.opentelemetry.config import OpenTelemetryConfig, ExporterType
```

| 환경변수 | 필드 | 타입 | 기본값 | 설명 |
|----------|------|------|--------|------|
| `SPAKKY_OTEL_SERVICE_NAME` | `service_name` | `str` | `"spakky-service"` | OTel 리소스의 `service.name` |
| `SPAKKY_OTEL_EXPORTER_TYPE` | `exporter_type` | `ExporterType` | `ExporterType.OTLP` | span exporter 유형 |
| `SPAKKY_OTEL_EXPORTER_ENDPOINT` | `exporter_endpoint` | `str` | `"http://localhost:4317"` | OTLP collector gRPC 엔드포인트 |
| `SPAKKY_OTEL_SAMPLE_RATE` | `sample_rate` | `float` (0.0~1.0) | `1.0` | 트레이스 샘플링 비율 |

### ExporterType

```python
from spakky.plugins.opentelemetry.config import ExporterType

class ExporterType(StrEnum):
    OTLP = "otlp"       # OTLPSpanExporter (gRPC)
    CONSOLE = "console"  # ConsoleSpanExporter (stdout)
    NONE = "none"        # exporter 없음 (전파만 수행)
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

`spakky-logging`이 설치되어 있으면, `LogContextBridge`를 사용하여 현재 `TraceContext`의 trace_id/span_id를 `LogContext`에 자동 바인딩할 수 있습니다.

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
LogContextBridge.sync()
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

OTLP exporter는 선택적 의존성입니다:

```bash
uv add "spakky-opentelemetry[otlp]"
```

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
