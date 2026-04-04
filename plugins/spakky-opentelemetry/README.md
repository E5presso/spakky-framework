# spakky-opentelemetry

OpenTelemetry SDK bridge for Spakky Framework.

`spakky-tracing`이 제공하는 `ITracePropagator` 인터페이스의 OpenTelemetry 구현체입니다. 플러그인을 설치하면 `OTelSetupPostProcessor`가 컨테이너의 `W3CTracePropagator`를 `OTelTracePropagator`로 자동 교체하여, OTel 백엔드(Jaeger, Grafana Tempo 등)와 연동합니다.

## spakky-tracing과의 관계

`spakky-tracing`은 `TraceContext`와 `ITracePropagator` 추상화를 제공하고, 기본 구현체로 `W3CTracePropagator`를 등록합니다. `spakky-opentelemetry`는 이 기본 구현체를 **런타임에 교체**합니다:

1. `OTelSetupPostProcessor`(`@Order(0)`)가 Pod 후처리 단계에서 `W3CTracePropagator` 인스턴스를 감지
2. 해당 인스턴스를 `OTelTracePropagator`로 교체하여 반환
3. 동시에 OTel `TracerProvider`를 설정 (exporter, sampler, resource)

따라서 `spakky-tracing`만 설치하면 순수 W3C TraceContext 전파가 동작하고, `spakky-opentelemetry`를 추가하면 OTel SDK 기반 전파로 업그레이드됩니다.

## Installation

```bash
pip install spakky-opentelemetry
```

OTLP exporter 사용 시:

```bash
pip install spakky-opentelemetry[otlp]
```

spakky-logging 브릿지 사용 시:

```bash
pip install spakky-opentelemetry[logging]
```

## Features

| 컴포넌트 | 역할 |
|---------|------|
| `OpenTelemetryConfig` | `@Configuration` — 환경변수 기반 OTel SDK 설정 |
| `OTelSetupPostProcessor` | `IPostProcessor` — TracerProvider 초기화 및 W3CTracePropagator 교체 |
| `OTelTracePropagator` | `ITracePropagator` 구현 — OTel SDK의 `TraceContextTextMapPropagator` 브릿지 |
| `LogContextBridge` | TraceContext의 trace_id/span_id를 `spakky-logging`의 `LogContext`에 동기화 (optional) |
| `ExporterType` | `StrEnum` — 지원 exporter 타입 (`otlp`, `console`, `none`) |

## Configuration

환경변수로 설정합니다 (`OpenTelemetryConfig`, env prefix: `SPAKKY_OTEL_`):

| 환경변수 | 기본값 | 설명 |
|---------|--------|------|
| `SPAKKY_OTEL_SERVICE_NAME` | `spakky-service` | OTel 서비스 이름 |
| `SPAKKY_OTEL_EXPORTER_TYPE` | `otlp` | 스팬 exporter (`otlp`, `console`, `none`) |
| `SPAKKY_OTEL_EXPORTER_ENDPOINT` | `http://localhost:4317` | OTLP collector 엔드포인트 |
| `SPAKKY_OTEL_SAMPLE_RATE` | `1.0` | 트레이스 샘플링 비율 (0.0~1.0) |

## Usage

플러그인은 `spakky.plugins` 엔트리 포인트로 자동 등록됩니다. `SpakkyApplication.load_plugins()`를 호출하면 자동으로 활성화됩니다.

```python
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins()  # spakky-opentelemetry 자동 로드
    .scan(my_module)
    .start()
)
```

### LogContext 브릿지

`spakky-logging`이 설치되어 있으면 `LogContextBridge.sync()`로 trace_id/span_id를 로그 컨텍스트에 바인딩할 수 있습니다. `spakky-logging`이 없으면 no-op으로 동작합니다:

```python
from spakky.plugins.opentelemetry.bridge import LogContextBridge

# TraceContext 설정 후
LogContextBridge.sync()  # LogContext에 trace_id, span_id 자동 바인딩
```

## License

MIT License
