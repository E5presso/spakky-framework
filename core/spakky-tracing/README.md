# Spakky Tracing

[Spakky Framework](https://github.com/E5presso/spakky-framework)를 위한 분산 트레이싱 추상화입니다.

## 설치

```bash
pip install spakky-tracing
```

## 주요 기능

- **`TraceContext`**: `contextvars`를 지원하는 W3C Trace Context Level 2 호환 trace context
- **`ITracePropagator`**: service boundary를 넘는 trace context propagation용 abstract interface
- **`W3CTracePropagator`**: 내장 W3C `traceparent` header propagator
- **Async-safe**: `asyncio` task별로 격리되는 `contextvars` 기반 context propagation
- **외부 의존성 없음**: 순수 Python 구현이며 `spakky` core에만 의존

## 빠른 시작

### TraceContext 생성과 전파

```python
from spakky.tracing.context import TraceContext

# 새 root trace 시작
ctx = TraceContext.new_root()
TraceContext.set(ctx)

# 현재 trace 접근
current = TraceContext.get()
print(current.to_traceparent())
# 00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01

# child span 생성
child = current.child()
TraceContext.set(child)
```

### 들어오는 trace header 파싱

```python
from spakky.tracing.context import TraceContext

header = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
ctx = TraceContext.from_traceparent(header)
```

### W3CTracePropagator로 주입/추출

```python
from spakky.tracing.w3c_propagator import W3CTracePropagator

propagator = W3CTracePropagator()

# 현재 trace를 outgoing header에 주입
carrier: dict[str, str] = {}
propagator.inject(carrier)
# carrier == {"traceparent": "00-...-...-01"}

# incoming header에서 trace 추출
ctx = propagator.extract(carrier)
```

## 라이선스

MIT License
