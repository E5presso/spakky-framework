# Actuator 상태 확인

`spakky-actuator`는 애플리케이션 상태를 transport-neutral 모델로 집계합니다.
FastAPI와 Typer 플러그인은 같은 core result를 HTTP endpoint나 CLI command로 노출합니다.

## 의미 구분

| Surface | 용도 | 실패 기준 |
|---------|------|-----------|
| `health` | 운영자가 보는 전체 상태 | required probe 중 하나라도 unhealthy이면 unhealthy |
| `readiness` | 트래픽이나 작업을 받을 준비 여부 | 외부 의존성 등 준비 상태 probe 실패를 반영 |
| `liveness` | 프로세스와 프레임워크 기본 생존 여부 | readiness와 분리되며 기본 probe가 없으면 healthy baseline |
| `info` | 앱 버전, 빌드, 런타임 metadata | 등록된 contributor payload를 deterministic merge |

기본 health probe는 `health`와 `readiness`에만 참여합니다.
`liveness`는 데이터베이스, 브로커, 외부 API 같은 dependency readiness와 분리해야 합니다.

## Core 사용

```python
from spakky.actuator import (
    AbstractHealthProbe,
    ActuatorAggregationService,
    ActuatorEndpoint,
    ActuatorExtensionRegistry,
    ComponentHealthResult,
)


class DatabaseProbe(AbstractHealthProbe):
    @property
    def name(self) -> str:
        return "database"

    def check(self) -> ComponentHealthResult:
        return ComponentHealthResult.healthy(self.name)


class ProcessProbe(AbstractHealthProbe):
    @property
    def name(self) -> str:
        return "process"

    @property
    def endpoints(self) -> tuple[ActuatorEndpoint, ...]:
        return (ActuatorEndpoint.LIVENESS,)

    def check(self) -> ComponentHealthResult:
        return ComponentHealthResult.healthy(self.name)


registry = ActuatorExtensionRegistry()
registry.register_health_probe(DatabaseProbe())
registry.register_health_probe(ProcessProbe())

service = ActuatorAggregationService(registry)
readiness = service.evaluate_readiness()
liveness = service.evaluate_liveness()
```

`ComponentHealthResult.unhealthy(..., required=False)`는 component 자체는 unhealthy로 보존하지만 aggregate status를 실패시키지 않습니다.
`ActuatorConfig(include_details=False)`를 등록하면 component details 노출을 제한합니다.

## DI 확장

애플리케이션에서는 probe와 info contributor를 Pod로 등록하면 됩니다.
`spakky-actuator` plugin이 `ActuatorExtensionPostProcessor`를 등록하고, DI-managed extension을 `ActuatorExtensionRegistry`에 모읍니다.

```python
from collections.abc import Mapping

from spakky.actuator import IInfoContributor
from spakky.core.pod.annotations.pod import Pod


@Pod()
class BuildInfo(IInfoContributor):
    @property
    def name(self) -> str:
        return "build"

    def contribute_info(self) -> Mapping[str, object]:
        return {"version": "1.0.0"}
```

Async probe와 async info contributor도 지원합니다.
동기 평가 메서드에서 async extension이 발견되면 명시적 actuator error가 발생하므로, async transport에서는 `evaluate_*_async()`를 사용하세요.

## FastAPI 노출

`spakky-actuator`와 `spakky-fastapi`를 함께 로드하면 다음 route가 등록됩니다.

| Route | Healthy | Unhealthy |
|-------|---------|-----------|
| `GET /actuator/health` | `200 OK` | `503 Service Unavailable` |
| `GET /actuator/readiness` | `200 OK` | `503 Service Unavailable` |
| `GET /actuator/liveness` | `200 OK` | `503 Service Unavailable` |
| `GET /actuator/info` | `200 OK` | N/A |

`FastAPIActuatorConfig`로 base path와 endpoint별 노출 여부를 조정합니다.

```python
from spakky.core.pod.annotations.pod import Pod
from spakky.plugins.fastapi.actuator import FastAPIActuatorConfig


@Pod()
def fastapi_actuator_config() -> FastAPIActuatorConfig:
    return FastAPIActuatorConfig(
        base_path="/internal/actuator",
        readiness_enabled=False,
    )
```

## Typer 노출

`spakky-actuator`와 `spakky-typer`를 함께 로드하면 `actuator` command group이 등록됩니다.

```bash
python main.py actuator health
python main.py actuator readiness
python main.py actuator liveness
python main.py actuator info
```

다음 환경변수로 command 노출을 제어합니다.

```bash
export SPAKKY_TYPER_ACTUATOR_COMMAND_ENABLED=false
export SPAKKY_TYPER_ACTUATOR_COMMAND_NAME=status
```

## 범위 밖

이번 actuator MVP는 plugin-specific deep health checks를 제공하지 않습니다.
SQLAlchemy 연결, Kafka/RabbitMQ broker, Celery worker 같은 깊은 통합 상태는 각 앱이 `AbstractHealthProbe`로 추가합니다.
Metrics exporter나 Prometheus/OpenTelemetry exporter 약속도 이 milestone 범위가 아닙니다.
