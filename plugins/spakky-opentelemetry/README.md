# spakky-opentelemetry

OpenTelemetry SDK bridge for Spakky Framework.

`spakky-tracing`의 `ITracePropagator` 인터페이스를 OpenTelemetry SDK의 propagation API로 구현하여, OTel 백엔드(Jaeger, Grafana Tempo 등)와 연동합니다.

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

## Configuration

환경변수로 설정합니다:

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

`spakky-logging`이 설치되어 있으면 `LogContextBridge.sync()`로 trace_id/span_id를 로그 컨텍스트에 바인딩할 수 있습니다:

```python
from spakky.plugins.opentelemetry.bridge import LogContextBridge

# TraceContext 설정 후
LogContextBridge.sync()  # LogContext에 trace_id, span_id 자동 바인딩
```

## License

MIT License
