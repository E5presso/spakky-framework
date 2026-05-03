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

## License

MIT License
