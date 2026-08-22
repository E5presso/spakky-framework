# spakky-opentelemetry

> Spakky Framework를 OpenTelemetry SDK에 연결하는 observability bridge입니다.
> `spakky-tracing`의 W3C propagator를 OpenTelemetry propagator로 교체하고, `spakky-agent`의 privacy-safe telemetry를 exact OTel span으로 저장하며, 선택적으로 logging context와 trace context를 동기화합니다.

`spakky-tracing`이 제공하는 `ITracePropagator`와 `spakky-agent`이 제공하는 `IAgentTelemetry` 두 port의 OpenTelemetry 구현체입니다. 플러그인을 설치하면 `OTelSetupPostProcessor`가 컨테이너의 `W3CTracePropagator`를 `OTelTracePropagator`로 교체하고 `OpenTelemetryAgentTelemetry`를 `IAgentTelemetry`에 bind하여 OTel 백엔드(Jaeger, Grafana Tempo 등)와 연동합니다.

## spakky-tracing과의 관계

`spakky-tracing`은 `TraceContext`와 `ITracePropagator` 추상화를 제공하고, 기본 구현체로 `W3CTracePropagator`를 등록합니다. `spakky-opentelemetry`는 이 기본 구현체를 **런타임에 교체**합니다:

1. `OTelSetupPostProcessor`(`@Order(0)`)가 Pod 후처리 단계에서 `W3CTracePropagator` 인스턴스를 감지
2. 해당 인스턴스를 `OTelTracePropagator`로 교체하여 반환
3. 동시에 OTel `TracerProvider`를 설정 (exporter, sampler, resource)

따라서 `spakky-tracing`만 설치하면 순수 W3C TraceContext 전파가 동작하고, `spakky-opentelemetry`를 추가하면 OTel SDK 기반 전파로 업그레이드됩니다.

## 설치

```bash
pip install spakky-opentelemetry
```

spakky-logging 브릿지 사용 시:

```bash
pip install spakky-opentelemetry[logging]
```

## 주요 기능

| 컴포넌트 | 역할 |
|---------|------|
| `OpenTelemetryConfig` | `@Configuration` — 환경변수 기반 OTel SDK 설정 |
| `OTelSetupPostProcessor` | `IPostProcessor` — TracerProvider 초기화 및 W3CTracePropagator 교체 |
| `OTelTracePropagator` | `ITracePropagator` 구현 — OTel SDK의 `TraceContextTextMapPropagator` 브릿지 |
| `OpenTelemetryAgentTelemetry` | `IAgentTelemetry` 구현 — completed Agent operation을 exact timestamp/parent/status의 OTel span으로 기록 |
| `LogContextBridge` | TraceContext의 trace_id/span_id를 `spakky-logging`의 `LogContext`에 동기화 (선택) |
| `ExporterType` | `StrEnum` — 지원 exporter 타입 (`otlp`, `console`, `none`) |

## 설정

환경변수로 설정합니다 (`OpenTelemetryConfig`, env prefix: `SPAKKY_OTEL_`):

| 환경변수 | 기본값 | 설명 |
|---------|--------|------|
| `SPAKKY_OTEL_SERVICE_NAME` | `spakky-service` | OTel 서비스 이름 |
| `SPAKKY_OTEL_EXPORTER_TYPE` | `otlp` | 스팬 exporter (`otlp`, `console`, `none`) |
| `SPAKKY_OTEL_EXPORTER_ENDPOINT` | `http://localhost:4317` | OTLP collector 엔드포인트 |
| `SPAKKY_OTEL_SAMPLE_RATE` | `1.0` | 트레이스 샘플링 비율 (0.0~1.0) |

## 사용법

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

### Agent telemetry

Plugin initialization은 `OpenTelemetryAgentTelemetry`를 Pod로 등록하고 `IAgentTelemetry`에 bind합니다. `AgentRunnerFactory`는 이 optional port를 열린 runner에 적용하므로 application이 prompt나 tool body를 OTel API에 직접 전달할 필요가 없습니다.

| Agent kind | `gen_ai.operation.name` | OTel `SpanKind` |
|------------|-------------------------|-----------------|
| `RUN` | `invoke_agent` | `INTERNAL` |
| `MODEL` | `generate_content` | `CLIENT` |
| `TOOL` | `execute_tool` | `INTERNAL` |
| `RETRIEVAL` | `retrieval` | `CLIENT` |

`AgentSpanRecord.started_at_ns`/`ended_at_ns`를 `Tracer.start_span(start_time=...)`/`Span.end(end_time=...)`에 그대로 넘겨 runner가 완료 시점에 내보낸 시간을 재생합니다. `AgentSpanStatus.OK`는 OTel `StatusCode.OK`, `ERROR` + `error_code`는 `StatusCode.ERROR` description과 `error.type`으로 매핑합니다. Caller가 넣은 `gen_ai.operation.name`/`error.type`은 무시하고 adapter의 semantic 값을 사용합니다.

Parent는 ambient OTel current span을 묵묵히 상속하지 않습니다. `TraceContext.get()`이 있으면 `OTelContextConverter`가 같은 trace/span id·flags의 non-recording parent context를 만들고, 없으면 explicit empty OTel context를 넘겨 root span을 만듭니다. Agent RUN/MODEL/TOOL/RETRIEVAL record 사이에서 자동 parent/child 계층을 추론하지 않습니다.

Core가 허용한 scalar attributes만 OTel로 전달합니다. Adapter는 prompt/system instruction, input/output messages, context/retrieval body/query, tool arguments/result와 대표 raw-body key를 case-insensitive denylist로 한 번 더 제거합니다. Run/conversation id, model route·usage·cost, tool name/identity/kind, classic retrieval count/limit·bound scope처럼 body가 아닌 scalar만 남습니다.

### LogContext 브릿지

`spakky-logging`이 설치되어 있으면 `LogContextBridge` pod instance의 `sync()`를 호출하여 trace_id/span_id를 로그 컨텍스트에 바인딩할 수 있습니다. `spakky-logging`이 없으면 no-op으로 동작합니다:

```python
from spakky.plugins.opentelemetry.bridge import LogContextBridge

# TraceContext 설정 후
bridge = app.container.get(type_=LogContextBridge)
bridge.sync()  # LogContext에 trace_id, span_id 바인딩
```

## 의존성 경계

Spakky 패키지 간 production dependency는 `spakky` core, `spakky-tracing`, `spakky-agent`입니다. `spakky-llm`나 다른 plugin을 import하지 않으며 Agent semantic은 core `AgentSpanRecord`로만 받습니다. `spakky-logging`은 `[logging]` extra일 때만 사용하고 설치되지 않으면 `LogContextBridge` 경로는 no-op입니다.

OTel API/SDK, exporter와 `pydantic-settings`는 외부 dependency입니다. 이 plugin은 raw Agent body를 수집하는 다른 telemetry backend을 자동 추가하지 않습니다.

## 관련 결정

- [ADR-0020: Semantic memory, evaluation, pricing과 Agent telemetry](../../docs/adr/0020-agent-memory-evaluation-cost-telemetry.md)

## 개발 검증

패키지 단위 검증은 해당 패키지 디렉토리에서 실행합니다.

```bash
uv run ruff format .
uv run ruff check .
uv run pyrefly check src tests --min-severity warn --no-progress-bar --output-format min-text
uv run pytest
```

`pytest`는 각 패키지 `pyproject.toml`의 coverage 설정을 사용합니다.

## 라이선스

MIT License
