# Spakky Tracing

Distributed tracing abstraction for [Spakky Framework](https://github.com/E5presso/spakky-framework).

## Installation

```bash
pip install spakky-tracing
```

## Features

- **`TraceContext`**: W3C Trace Context Level 2 compatible trace context with `contextvars` support
- **`ITracePropagator`**: Abstract interface for trace context propagation across service boundaries
- **`W3CTracePropagator`**: Built-in W3C `traceparent` header propagator
- **Async-safe**: `contextvars`-based context propagation, isolated per `asyncio` task
- **Zero external dependencies**: Pure Python implementation, depends only on `spakky` core

## Quick Start

### Create and Propagate Trace Context

```python
from spakky.tracing.context import TraceContext

# Start a new root trace
ctx = TraceContext.new_root()
TraceContext.set(ctx)

# Access current trace
current = TraceContext.get()
print(current.to_traceparent())
# 00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01

# Create a child span
child = current.child()
TraceContext.set(child)
```

### Parse Incoming Trace Headers

```python
from spakky.tracing.context import TraceContext

header = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
ctx = TraceContext.from_traceparent(header)
```

### Use W3CTracePropagator for Injection/Extraction

```python
from spakky.tracing.w3c_propagator import W3CTracePropagator

propagator = W3CTracePropagator()

# Inject current trace into outgoing headers
carrier: dict[str, str] = {}
propagator.inject(carrier)
# carrier == {"traceparent": "00-...-...-01"}

# Extract trace from incoming headers
ctx = propagator.extract(carrier)
```

## License

MIT License
