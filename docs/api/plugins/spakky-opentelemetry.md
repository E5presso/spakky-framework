# spakky-opentelemetry

> `spakky-opentelemetry`는 Spakky `TraceContext` propagation과 privacy-safe Agent telemetry를 OpenTelemetry SDK에 연결합니다.

플러그인 initialize 단계에서 `OpenTelemetryAgentTelemetry`를 Pod로 등록하고
`IAgentTelemetry`에 bind합니다. Injected `AgentRunnerFactory`가 이 binding을 사용하며,
export 여부와 endpoint/sample rate는 기존 `OpenTelemetryConfig`가 소유합니다.

Agent bridge는 core `AgentSpanRecord`의 exact nanosecond interval, scalar attributes,
OK/ERROR status를 OTel span으로 옮깁니다. Ambient Spakky `TraceContext`가 있으면 그
trace/span을 parent로 보존합니다. Prompt/context/system instructions/completion, retrieval
query/content, tool arguments/results key는 exporter 전에 제거하고
`gen_ai.operation.name`과 optional `error.type`은 adapter가 결정합니다.

사용 흐름은 [OpenTelemetry 통합](../../guides/opentelemetry.md), core pricing/telemetry와의
결합은 [Agent Memory, Evaluation, Cost와 Telemetry](../../guides/agent-operations.md)를
확인하세요.

## 브릿지

::: spakky.plugins.opentelemetry.bridge
    options:
      show_root_heading: false

## Propagator

::: spakky.plugins.opentelemetry.propagator
    options:
      show_root_heading: false

## Agent telemetry

::: spakky.plugins.opentelemetry.telemetry
    options:
      show_root_heading: false

## 후처리기

::: spakky.plugins.opentelemetry.post_processor
    options:
      show_root_heading: false

## 설정

::: spakky.plugins.opentelemetry.config
    options:
      show_root_heading: false

## 에러

::: spakky.plugins.opentelemetry.error
    options:
      show_root_heading: false

## 추가 모듈

::: spakky.plugins.opentelemetry.main
    options:
      show_root_heading: false
