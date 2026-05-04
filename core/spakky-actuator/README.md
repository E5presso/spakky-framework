# Spakky Actuator

[Spakky Framework](https://github.com/E5presso/spakky-framework)를 위한 transport 중립 actuator 계약입니다.

## 설치

```bash
pip install spakky-actuator
```

## 주요 기능

- **Health/readiness/liveness 결과**: HTTP, CLI 등 adapter가 공유하는 result 계약
- **Probe 확장 지점**: Spakky DI로 등록되는 동기/비동기 health probe
- **Info contributor**: 동기/비동기 info contributor의 결정적 병합
- **Startup diagnostics contributor**: `SpakkyApplication` startup report를 actuator info로 노출
- **예외 처리**: Probe 예외를 구조화된 에러 상세가 포함된 비정상 component result로 변환
- **Transport 중립 core**: FastAPI, Typer, plugin adapter 의존성 없음

## Endpoint Semantics

| Surface | Meaning | Default behavior |
|---------|---------|------------------|
| `health` | operator-facing status check용 aggregate application health | `ActuatorEndpoint.HEALTH`를 `endpoints`에 포함하는 probe 평가 |
| `readiness` | app이 traffic 또는 work를 받을 준비가 되었는지 | readiness probe 평가; 필수 unhealthy probe가 있으면 결과 unhealthy |
| `liveness` | process/framework 생존 여부 | 외부 dependency readiness와 분리; custom liveness probe가 없으면 healthy baseline 반환 |
| `info` | 결정적 application metadata | 등록된 info contributor를 contributor 이름 기준으로 병합 |

기본적으로 health probe는 `liveness`가 아니라 `health`와 `readiness`에 참여합니다.
외부 의존성을 사용할 수 없다는 이유로 실패하면 안 되는 프로세스 내부 check에만 `ActuatorEndpoint.LIVENESS`를 사용하세요.

## 빠른 시작

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

Component health를 제공하려면 `AbstractHealthProbe` 또는 `AbstractAsyncHealthProbe` Pod를 등록하세요.
`info`에 metadata를 제공하려면 `IInfoContributor` 또는 `IAsyncInfoContributor` Pod를 등록하세요.
Actuator 플러그인은 `ActuatorExtensionPostProcessor`를 추가하여 해당 Pod를 발견하고 `ActuatorExtensionRegistry`에 저장합니다.

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

Backend plugin은 자신이 소유한 외부 의존 상태를 first-party probe/contributor로 등록합니다. 예를 들어 `spakky-redis`는 Redis 연결 상태와 cache metrics를 actuator health/info에 연결합니다. 애플리케이션은 transport adapter를 바꾸지 않고 같은 계약으로 자체 check를 추가할 수 있습니다.

## 라이선스

MIT License
