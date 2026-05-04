# Actuator 상태 확인

`spakky-actuator`는 애플리케이션 상태를 transport-neutral 모델로 집계합니다.
FastAPI와 Typer 플러그인은 같은 core result를 HTTP 엔드포인트나 CLI 명령으로 노출합니다.

## 의미 구분

| 표면 | 용도 | 실패 기준 |
|---------|------|-----------|
| `health` | 운영자가 보는 전체 상태 | 필수 probe 중 하나라도 비정상이면 비정상 |
| `readiness` | 트래픽이나 작업을 받을 준비 여부 | 외부 의존성 등 준비 상태 probe 실패를 반영 |
| `liveness` | 프로세스와 프레임워크 기본 생존 여부 | readiness와 분리되며 기본 probe가 없으면 정상 baseline |
| `info` | 앱 버전, 빌드, 런타임 metadata | 등록된 contributor payload를 결정적으로 병합 |

기본 health probe는 `health`와 `readiness`에만 참여합니다.
`liveness`는 데이터베이스, 브로커, 외부 API 같은 의존성 readiness와 분리해야 합니다.

## 코어 사용

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

비동기 probe와 비동기 info contributor도 지원합니다.
동기 평가 메서드에서 비동기 extension이 발견되면 명시적 actuator 에러가 발생하므로, 비동기 transport에서는 `evaluate_*_async()`를 사용하세요.

## FastAPI 노출

`spakky-actuator`와 `spakky-fastapi`를 함께 로드하면 다음 route가 등록됩니다.

| Route | 정상 | 비정상 |
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

`spakky-actuator`와 `spakky-typer`를 함께 로드하면 `actuator` 명령 그룹이 등록됩니다.

```bash
python main.py actuator health
python main.py actuator readiness
python main.py actuator liveness
python main.py actuator info
```

다음 환경변수로 명령 노출을 제어합니다.

```bash
export SPAKKY_TYPER_ACTUATOR_COMMAND_ENABLED=false
export SPAKKY_TYPER_ACTUATOR_COMMAND_NAME=status
```

## Backend 제공 Probe

Actuator core는 transport-neutral registry와 aggregation을 담당합니다. Backend plugin은 자신이 소유한 외부 의존 상태를 first-party probe/contributor로 등록할 수 있습니다.

`spakky-redis`는 `RedisCacheHealthProbe`와 `RedisCacheMetricsInfoContributor`를 등록하여 Redis 연결 상태와 cache metrics를 actuator health/info 표면에 노출합니다. SQLAlchemy, Kafka/RabbitMQ, Celery 같은 다른 backend도 같은 `AbstractHealthProbe` / `IInfoContributor` 계약으로 확장합니다.
