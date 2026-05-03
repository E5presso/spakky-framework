# Spakky Actuator

Transport-neutral actuator contracts for [Spakky Framework](https://github.com/E5presso/spakky-framework).

## Installation

```bash
pip install spakky-actuator
```

## Features

- **Health, readiness, liveness results**: Shared result contracts for HTTP, CLI, or other adapters
- **Probe extension points**: Sync and async health probes registered through Spakky DI
- **Info contributors**: Deterministic merge of sync and async info contributors
- **Exception handling**: Probe exceptions become unhealthy component results with structured error details
- **Transport-neutral core**: No FastAPI, Typer, or plugin adapter dependency

## Endpoint Semantics

| Surface | Meaning | Default behavior |
|---------|---------|------------------|
| `health` | Aggregate application health for operator-facing status checks | Evaluates probes whose `endpoints` include `ActuatorEndpoint.HEALTH` |
| `readiness` | Whether the app is ready to serve traffic or work | Evaluates readiness probes; required unhealthy probes make the result unhealthy |
| `liveness` | Whether the process/framework is alive | Separate from external dependency readiness; no custom liveness probes returns a healthy baseline |
| `info` | Deterministic application metadata | Merges registered info contributors by contributor name |

By default, health probes participate in `health` and `readiness`, not `liveness`.
Use `ActuatorEndpoint.LIVENESS` only for process-local checks that should not fail because an external dependency is unavailable.

## Quick Start

```python
from spakky.actuator import (
    AbstractHealthProbe,
    ActuatorAggregationService,
    ActuatorExtensionRegistry,
    ComponentHealthResult,
)


class DatabaseProbe(AbstractHealthProbe):
    @property
    def name(self) -> str:
        return "database"

    def check(self) -> ComponentHealthResult:
        return ComponentHealthResult.healthy(self.name)


registry = ActuatorExtensionRegistry()
registry.register_health_probe(DatabaseProbe())

service = ActuatorAggregationService(registry)
health = service.evaluate_health()
readiness = service.evaluate_readiness()
```

## Extension Points

Register `AbstractHealthProbe` or `AbstractAsyncHealthProbe` Pods to contribute component health.
Register `IInfoContributor` or `IAsyncInfoContributor` Pods to contribute metadata to `info`.
The actuator plugin adds `ActuatorExtensionPostProcessor`, which discovers those Pods and stores them in `ActuatorExtensionRegistry`.

```python
from spakky.actuator import (
    AbstractHealthProbe,
    IInfoContributor,
    ActuatorEndpoint,
    ComponentHealthResult,
)


class ProcessProbe(AbstractHealthProbe):
    @property
    def name(self) -> str:
        return "process"

    @property
    def endpoints(self) -> tuple[ActuatorEndpoint, ...]:
        return (ActuatorEndpoint.LIVENESS,)

    def check(self) -> ComponentHealthResult:
        return ComponentHealthResult.healthy(self.name)


class BuildInfo(IInfoContributor):
    @property
    def name(self) -> str:
        return "build"

    def contribute_info(self) -> dict[str, object]:
        return {"version": "1.0.0"}
```

Plugin-specific deep checks for SQLAlchemy, Kafka, RabbitMQ, Celery, or other integrations are intentionally not included in this milestone.
Applications can add those checks as first-party probes without changing the transport adapters.

## License

MIT License
