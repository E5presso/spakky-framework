# ADR-0004: 분산 트레이싱 아키텍처 — `spakky-tracing` 코어 + OTel 플러그인 분리

- **상태**: Accepted
- **날짜**: 2026-03-15

## 맥락 (Context)

Spakky Framework의 `LogContext`는 `contextvars` 기반으로 **단일 프로세스 내**에서만 동작한다. 마이크로서비스 환경(FastAPI → RabbitMQ → Celery → Celery)에서 `trace_id`가 프로세스 경계를 넘지 못하여, 하나의 요청이 여러 서비스를 거칠 때 로그를 연결할 수 없다.

현재 프레임워크의 갭:

- `IEventTransport.send(event_name, payload)` — 메타데이터/헤더 파라미터가 없음
- RabbitMQ 전송: `Message(body=payload)` — AMQP headers 미사용
- Kafka 전송: `producer.produce(value=payload)` — record headers 미사용
- Consumer 측: body만 역직렬화, 메타데이터 추출 없음
- Celery: EventTransport 구현 자체가 없고, task 디스패치 시 context 전파 없음
- FastAPI: 수신 HTTP 요청의 `traceparent` 헤더를 파싱하지 않음

프레임워크 사용자는 AWS X-Ray, Sentry, Jaeger 등 다양한 관측 가능성(Observability) 백엔드와 연동할 수 있어야 하며, 향후 gRPC, WebSocket 등 새로운 통신 프로토콜로의 확장도 가능해야 한다.

### 선행 조사: 주요 프레임워크의 접근 방식

| 프레임워크        | 핵심 추상화                                 | OTel 관계              | 컨텍스트 저장     | 메시징 전파               |
| ----------------- | ------------------------------------------- | ---------------------- | ----------------- | ------------------------- |
| **Spring Boot**   | Micrometer `Observation` + `Tracer` facade  | bridge 패턴 (플러그인) | ThreadLocal       | Template이 headers inject |
| **ASP.NET Core**  | `System.Diagnostics.Activity` (런타임 내장) | 선택적 addon           | ExecutionContext  | 메시징 라이브러리 책임    |
| **OpenTelemetry** | `Context` + `TextMapPropagator`             | 표준 자체              | language-specific | Carrier + Propagator      |

세 프레임워크 모두 **자체 추상화 레이어**를 가지고 있으며, OTel은 직접 의존하지 않고 bridge/addon으로 연결하는 패턴이 공통적이다. Python은 .NET과 달리 런타임에 트레이싱 지원이 없으므로, 프레임워크가 그 역할을 해야 한다.

## 결정 동인 (Decision Drivers)

- **외부 의존성 최소화**: 코어 패키지에 `opentelemetry-api` 등 외부 라이브러리 의존 금지
- **자동 전파**: 개발자가 inject/extract를 직접 호출하지 않아도 trace가 서비스 간 전파
- **관심사 분리**: 트레이싱(trace_id 전파) ≠ 로깅(구조화 로그 출력)
- **Propagation 포맷 교체 가능**: W3C TraceContext, B3, AWS X-Ray 등
- **프로토콜 확장성**: HTTP, AMQP, Kafka, Celery, gRPC, WebSocket 등 모든 통신 경계에서 동일한 propagation 인터페이스
- **DX(개발자 경험)**: 플러그인 등록만으로 동작, 비즈니스 코드 수정 불필요

## 고려한 대안 (Considered Options)

### 대안 A: `IEventTransport`에 `headers` 파라미터만 추가

```python
class IEventTransport(ABC):
    @abstractmethod
    def send(self, event_name: str, payload: bytes, headers: dict[str, str] | None = None) -> None: ...
```

- 장점: 최소 변경, headers 채널 확보
- 단점: propagation 로직이 사용자 책임, 로그 자동 연동 불가, 프레임워크가 trace를 모름

### 대안 B: Envelope 패턴 (payload 내 메타데이터 포함)

```python
envelope = {"headers": {"trace_id": "..."}, "payload": original_payload}
```

- 장점: 인터페이스 변경 없음
- 단점: payload 오염, 직렬화/역직렬화 이중 처리, 브로커 네이티브 headers 기능 활용 불가, 기존 consumer와 비호환

### 대안 C: `ITracePropagator` 추상화 + AOP (코어 인터페이스 변경 없이)

- 장점: OTel 호환 설계, 코어 변경 없음
- 단점: 메타데이터 전달 채널(headers)이 없으면 propagator만으로는 불충분 — 결국 A 또는 B와 결합해야 함

### 대안 D: 코어에 `opentelemetry-api` 직접 의존

- 장점: OTel 생태계(propagator, exporter) 그대로 활용
- 단점: 코어에 외부 의존성 추가, OTel이 필요 없는 사용자에게도 강제, Spring Boot/ASP.NET Core의 접근 방식과 불일치

### 대안 E: `headers` 채널 + `ITracePropagator` 추상화 + OTel 플러그인 분리 ✅

A + C를 결합하되, 트레이싱을 별도 코어 패키지(`spakky-tracing`)로 분리하고, OTel 연동은 플러그인(`spakky-opentelemetry`)으로 제공.

- 장점: 코어에 외부 의존성 없음, 자동 전파, 포맷 교체 가능, Spring Boot의 Micrometer 패턴과 일치
- 단점: 새 코어 패키지 1개 추가, `IEventTransport` breaking change

## 결정 (Decision)

**대안 E**를 채택한다.

### 패키지 구조

| 계층         | 패키지                        | 역할                                                                                                        |
| ------------ | ----------------------------- | ----------------------------------------------------------------------------------------------------------- |
| **코어**     | `spakky-tracing` (신규)       | `TraceContext`, `ITracePropagator`, `W3CTracePropagator`, `TracingPlugin`                                   |
| **코어**     | `spakky-event` (수정)         | `IEventTransport.send()`에 `headers` 파라미터 추가                                                          |
| **코어**     | `spakky-logging` (무변경)     | `spakky-tracing`과 독립 — `spakky-opentelemetry`가 브릿지 역할                                              |
| **플러그인** | `spakky-fastapi` (수정)       | `TracingMiddleware` — HTTP 요청에서 extract, 응답에 inject                                                  |
| **플러그인** | `spakky-rabbitmq` (수정)      | Transport: headers inject / Consumer: headers extract                                                       |
| **플러그인** | `spakky-kafka` (수정)         | Transport: headers inject / Consumer: headers extract                                                       |
| **플러그인** | `spakky-celery` (수정)        | TaskDispatchAspect: headers inject / PostProcessor: headers extract                                         |
| **플러그인** | `spakky-opentelemetry` (신규) | `OTelTracePropagator` — OTel SDK bridge, exporter 설정, `spakky-logging` 설치 시 trace_id↔LogContext 브릿지 |

### 의존성 방향

```
spakky-tracing → spakky (코어 DI만 사용)
spakky-logging → spakky (코어 DI만 사용, tracing과 독립)
spakky-event → spakky-tracing (선택적 — 설치되어 있을 때만 propagator 사용)
각 플러그인 → spakky-tracing (설치되어 있을 때 ITracePropagator DI 주입)
spakky-opentelemetry → spakky-tracing + opentelemetry-api + opentelemetry-sdk
spakky-opentelemetry → spakky-logging (선택적 — 설치되어 있을 때 trace_id↔LogContext 브릿지)
```

### 핵심 인터페이스

```python
# spakky-tracing
class ITracePropagator(ABC):
    @abstractmethod
    def inject(self, carrier: dict[str, str]) -> None: ...

    @abstractmethod
    def extract(self, carrier: dict[str, str]) -> TraceContext | None: ...

    @abstractmethod
    def fields(self) -> list[str]: ...
```

```python
# spakky-event (수정)
class IEventTransport(ABC):
    @abstractmethod
    def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str] | None = None,
    ) -> None: ...
```

### TraceContext 접근성

`TraceContext`는 `contextvars` 기반이므로, 프레임워크가 관리하는 request scope 내 어디서든 접근 가능하다:

```python
from spakky.tracing.context import TraceContext

# 현재 실행 컨텍스트의 trace 정보를 어디서든 읽기
ctx = TraceContext.get()
ctx.trace_id       # "0af7651916cd43dd8448eb211c80319c"
ctx.span_id        # "b7ad6b7169203331"
ctx.to_traceparent()  # "00-0af7651916cd43dd...-b7ad6b7169203331-01"
```

trace 전파는 두 가지 경로로 나뉜다:

| 구분                        |          trace 전파           | 예시                                            |
| --------------------------- | :---------------------------: | ----------------------------------------------- |
| **First-party 플러그인**    |      **자동** (네이티브)      | EventBus, RabbitMQ, Kafka, Celery, FastAPI 수신 |
| **Third-party / 직접 호출** | **DI로 `TraceContext.get()`** | httpx, gRPC, WebSocket, 사용자 정의 통신        |

**First-party 플러그인**(`spakky-*`)은 trace를 네이티브하게 지원한다 — 플러그인 등록만으로 자동 inject/extract. 별도 코드 불필요.

**Third-party 라이브러리**나 프레임워크 외부의 통신에서는 개발자가 `TraceContext.get()`으로 현재 trace 정보를 읽어 직접 전달한다:

```python
@Pod()
class PaymentClient:
    async def charge(self, order_id: str) -> Result:
        ctx = TraceContext.get()
        return await httpx.post(
            "http://payment-service/pay",
            headers={"traceparent": ctx.to_traceparent()},
            json={"order_id": order_id},
        )
```

### 자동 전파 흐름 (프레임워크 관리 경로)

1. **HTTP 수신** (FastAPI `TracingMiddleware`):
   - `propagator.extract(request.headers)` → `TraceContext` 생성/복원
   - `LogContext.bind(trace_id=..., span_id=...)` 자동 실행

2. **EventBus 전송** (`DirectEventBus.send()`):
   - `propagator.inject(headers)` → 현재 `TraceContext`를 headers에 기록
   - `transport.send(event_name, payload, headers)` 호출

3. **메시지 수신** (RabbitMQ/Kafka Consumer):
   - `propagator.extract(message.headers)` → `TraceContext` 복원
   - `LogContext.bind(trace_id=..., span_id=...)` 자동 실행
   - 핸들러 실행

4. **Celery 디스패치** (`CeleryTaskDispatchAspect`):
   - `propagator.inject(task_headers)` → Celery task headers에 trace context 기록

5. **Celery 실행** (`CeleryPostProcessor`):
   - `propagator.extract(task.request.headers)` → `TraceContext` 복원
   - `LogContext.bind(...)` 자동 실행

### 설계 규칙

1. `W3CTracePropagator`는 W3C Trace Context Level 2 스펙의 `traceparent` 헤더를 파싱/생성한다. 외부 의존성 없이 순수 Python으로 구현한다.
2. `ITracePropagator`는 DI 컨테이너에 싱글턴으로 등록된다. `spakky-opentelemetry` 플러그인이 설치되면 기본 `W3CTracePropagator`를 `OTelTracePropagator`로 교체한다.
3. `TraceContext`는 `contextvars` 기반이며, 현재 request scope 내 어디서든 `TraceContext.get()`으로 접근 가능하다. `LogContext`와 독립적으로 존재하며, `spakky-opentelemetry`가 브릿지 역할을 하여 `spakky-logging`이 설치된 경우에만 `LogContext`에 `trace_id`, `span_id`를 자동 바인딩한다.
4. `headers` 파라미터는 `dict[str, str] | None = None`으로 선언하여 하위 호환성을 확보한다. 기존 Transport 구현체는 headers를 무시해도 동작한다.
5. 각 플러그인의 extract 시점에서 새 `span_id`를 생성하고, 수신된 `span_id`를 `parent_span_id`로 설정한다 (span 트리 구성).
6. 프레임워크 외부의 통신(HTTP, gRPC 등)에서 trace를 전파하려면 `TraceContext.get()`으로 현재 컨텍스트를 읽어 직접 헤더에 포함한다. 프레임워크는 outbound HTTP 클라이언트 래퍼를 제공하지 않는다 — 이는 DI 프레임워크의 책임 경계 밖이다.

## 결과 (Consequences)

### 긍정적

- **비즈니스 코드 수정 없이** 서비스 간 trace_id 연결 — 플러그인 등록만으로 동작
- `LogContext`와 자동 연동되어 구조화 로그에 `trace_id` 포함 — `grep`만으로 전체 서비스 스택 추적 가능
- `ITracePropagator` 교체로 W3C, B3, AWS X-Ray 등 다양한 propagation 포맷 지원
- OTel 플러그인 추가만으로 X-Ray/Sentry/Jaeger 대시보드 연동
- Spring Boot의 Micrometer Tracing과 동일한 아키텍처 패턴 — 업계 검증된 설계

### 부정적

- 새 코어 패키지(`spakky-tracing`) 추가로 모노레포 패키지 수 증가
- `IEventTransport` 시그니처 변경은 **breaking change** — 모든 Transport 구현체 수정 필요
- Consumer 측에서 headers가 없는 메시지(구버전 producer)를 수신할 경우 trace가 끊김 (graceful degradation: 새 trace 시작)

### 중립적

- `spakky-tracing` 없이 `spakky-event`를 사용하면 headers가 항상 `None`으로 전달됨 — 기존 동작과 동일
- `spakky-opentelemetry`는 선택적이므로, OTel이 필요 없는 프로젝트에 영향 없음
- W3C `traceparent` 파싱은 순수 문자열 처리로 구현 가능하므로 코어에 외부 의존성 불필요

## 참고 자료

- [W3C Trace Context Level 2](https://www.w3.org/TR/trace-context-2/)
- [OpenTelemetry Propagators API Spec](https://opentelemetry.io/docs/specs/otel/context/api-propagators/)
- [Spring Boot Tracing (Micrometer)](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [ASP.NET Core Distributed Tracing Concepts](https://learn.microsoft.com/en-us/dotnet/core/diagnostics/distributed-tracing-concepts)
- [ADR-0001: 이벤트 시스템 재설계](0001-event-system-redesign.md)
