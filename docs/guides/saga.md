# 사가 오케스트레이션

`spakky-saga`는 분산 트랜잭션의 보상(compensation) 기반 롤백을 오케스트레이션합니다. `SagaFlow`, `SagaStep`, `Transaction`, `Parallel`을 조합하여 비즈니스 프로세스를 선언적으로 모델링합니다.

---

## 동작 원리

1. `@Saga` 스테레오타입으로 사가 오케스트레이터 클래스를 DI 컨테이너에 등록
2. `@saga_step` 데코레이터로 사가 step 메서드를 `SagaStep` 디스크립터로 감쌈
3. `>>` (action + compensate), `&` (병렬), `|` (에러 전략) 연산자 또는 빌더 함수 `step()`, `parallel()`, `saga_flow()`로 실행 흐름을 DSL로 조합
4. `AbstractSaga.execute(data)` 또는 `run_saga_flow(flow, data)`가 흐름을 실행하고 `SagaResult`를 반환
5. step 실패 시 `ErrorStrategy`(Compensate/Skip/Retry)에 따라 분기하고, 필요 시 commit된 step을 역순으로 보상

---

## 설정

`spakky-saga`는 `spakky`와 `spakky-domain`에 의존합니다.

```bash
pip install spakky-saga
```

`@Saga()`는 `Pod`의 서브클래스이므로, 패키지 스캔만으로 DI 컨테이너가 사가 클래스를 자동 관리합니다. 별도 post-processor 등록은 필요하지 않습니다.

```python
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
import spakky.saga
import apps

app = (
    SpakkyApplication(ApplicationContext())
    .load_plugins(include={spakky.saga.PLUGIN_NAME})
    .scan(apps)
    .start()
)
```

---

## 사가 정의

### AbstractSagaData

사가 비즈니스 데이터 모델은 `AbstractSagaData`를 상속합니다. `@immutable` + `AbstractDomainModel` 기반이며, 각 step에는 읽기 전용으로 전달됩니다. `saga_id: UUID` 필드가 기본 제공됩니다.

```python
from spakky.core.common.mutability import immutable
from spakky.saga import AbstractSagaData


@immutable
class OrderSagaData(AbstractSagaData):
    order_id: str
    customer_id: str
    total_amount: float
```

### @Saga + AbstractSaga + @saga_step

`@Saga()`는 DI 컨테이너에 사가 클래스를 등록하는 스테레오타입입니다. `AbstractSaga[SagaDataT]`를 상속하여 `flow()`를 구현하면 `execute(data)`가 정의된 흐름을 실행합니다.

step으로 쓸 async 메서드에는 `@saga_step` 데코레이터를 붙여야 `>>`, `&`, `|` 연산자를 타입 안전하게 사용할 수 있습니다.

```python
from spakky.saga import AbstractSaga, Saga, SagaFlow, saga_flow, saga_step


@Saga()
class OrderSaga(AbstractSaga[OrderSagaData]):
    @saga_step
    async def create_order(self, data: OrderSagaData) -> OrderSagaData:
        ...

    @saga_step
    async def cancel_order(self, data: OrderSagaData) -> None:
        ...

    @saga_step
    async def reserve_stock(self, data: OrderSagaData) -> OrderSagaData:
        ...

    @saga_step
    async def release_stock(self, data: OrderSagaData) -> None:
        ...

    @saga_step
    async def process_payment(self, data: OrderSagaData) -> OrderSagaData:
        ...

    @saga_step
    async def refund_payment(self, data: OrderSagaData) -> None:
        ...

    def flow(self) -> SagaFlow[OrderSagaData]:
        return saga_flow(
            self.create_order >> self.cancel_order,
            self.reserve_stock >> self.release_stock,
            self.process_payment >> self.refund_payment,
        )
```

### step 시그니처 규약

| 역할 | 시그니처 | 반환값 |
|------|---------|--------|
| action (commit) | `async def(self, data: T) -> T \| None` | 변경된 `data` 또는 `None` (변경 없음) |
| compensate | `async def(self, data: T) -> None` | 부수효과만 수행, 반환값 없음 |

action이 새 `AbstractSagaData` 인스턴스를 반환하면 엔진이 이후 step들에 전달되는 `data`를 해당 값으로 갱신합니다.

---

## SagaFlow DSL

### 연산자

| 연산자 | 좌변 | 우변 | 결과 타입 |
|--------|------|------|----------|
| `>>` | `SagaStep` | `SagaStep` 또는 compensate 함수 | `Transaction` |
| `&` | `SagaStep` / `Transaction` / `Parallel` | 동일 | `Parallel` (최소 2개) |
| `\|` | `SagaStep` / `Transaction` | `ErrorStrategy` | 전략이 적용된 동일 타입 |

### 빌더 함수

```python
from spakky.saga import parallel, saga_flow, step
```

- `step(action, *, compensate=None, on_error=None, timeout=None)` — `SagaStep` 또는 `Transaction` 생성
- `parallel(*items)` — 동시 실행 그룹 (`Parallel`, 최소 2개). Callable은 자동으로 `SagaStep`으로 승격
- `saga_flow(*items)` — 최상위 흐름 (`SagaFlow`, 최소 1개)

### 흐름 조합 예시

```python
from datetime import timedelta

from spakky.saga import Retry, Skip, parallel, saga_flow, step


# 순차 실행
flow = saga_flow(
    step(saga.create_order),
    step(saga.reserve_stock),
    step(saga.process_payment),
)

# 보상 함수 지정 (Transaction 생성)
flow = saga_flow(
    step(saga.create_order, compensate=saga.cancel_order),
    step(saga.reserve_stock, compensate=saga.release_stock),
    step(saga.process_payment, compensate=saga.refund_payment),
)

# 병렬 실행
flow = saga_flow(
    step(saga.create_order, compensate=saga.cancel_order),
    parallel(
        step(saga.reserve_stock, compensate=saga.release_stock),
        step(saga.process_payment, compensate=saga.refund_payment),
    ),
)

# 에러 전략 + step 타임아웃
flow = saga_flow(
    step(saga.create_order, compensate=saga.cancel_order),
    step(saga.process_payment, timeout=timedelta(seconds=5)) | Retry(max_attempts=3),
    step(saga.log_analytics) | Skip(),
)
```

---

## 에러 전략 (ErrorStrategy)

step 실패 시 적용할 전략을 `|` 연산자 또는 `step(..., on_error=...)`로 지정합니다. 기본값은 `Compensate()`입니다.

| 전략 | 설명 |
|------|------|
| `Compensate()` | 역순 보상을 트리거하고 saga를 FAILED로 종료 (기본값) |
| `Skip()` | 실패를 무시하고 다음 step으로 진행 |
| `Retry(max_attempts, backoff, then)` | `max_attempts`회까지 재시도 후 `then` 전략 적용 |
| `ExponentialBackoff(base=1.0)` | `Retry.backoff`에 주입하는 지수 백오프. 지연 = `base * 2^(attempt-1)` |

```python
from spakky.saga import Compensate, ExponentialBackoff, Retry, Skip, step


# 기본 보상
step(saga.reserve_stock, compensate=saga.release_stock)  # on_error=Compensate()

# 3회 재시도 (실패 시 기본 Compensate)
step(saga.process_payment) | Retry(max_attempts=3)

# 지수 백오프 재시도
step(saga.send_notification) | Retry(
    max_attempts=5,
    backoff=ExponentialBackoff(base=2.0),
)

# 재시도 후 실패 무시
step(saga.log_analytics) | Retry(max_attempts=3, then=Skip())

# 실패 무시
step(saga.log_analytics) | Skip()
```

### v1 제약

- `parallel()` 그룹 내부의 step은 기본 `Compensate` 외 `on_error`를 지정할 수 없습니다. 지정 시 `SagaFlowDefinitionError`가 발생합니다.
- `parallel()` 그룹의 action 반환값은 v1에서 무시됩니다 (side-effect 전용). 순차 step은 정상적으로 `data`를 갱신합니다.

---

## 타임아웃

### step 타임아웃

`step(..., timeout=timedelta(...))`로 개별 step에 타임아웃을 적용합니다. 초과 시 `SagaStepTimeoutError`가 내부적으로 발생하며 `on_error` 전략을 거칩니다.

```python
from datetime import timedelta

step(saga.call_external_api, timeout=timedelta(seconds=3)) | Retry(max_attempts=2)
```

### saga 전체 타임아웃

`SagaFlow.timeout(duration)`으로 saga 전체 타임아웃을 설정합니다. 초과 시 `SagaStatus.TIMED_OUT`으로 종료되며, 그 시점까지 commit된 step은 역순으로 보상됩니다.

```python
from datetime import timedelta

flow = saga_flow(
    step(saga.create_order, compensate=saga.cancel_order),
    step(saga.process_payment, compensate=saga.refund_payment),
).timeout(timedelta(seconds=30))
```

> **제약**: saga 타임아웃이 `parallel()` 그룹 실행 도중 만료되면, 그 그룹 내에서 이미 성공했지만 `compensable` 리스트에 등록되기 전(gather 반환 전) 상태의 side-effect는 보상되지 않습니다. 순차 step이나 이미 완료된 parallel 그룹의 commit된 step은 정상 보상됩니다.

### 보상 실패 에스컬레이션

보상 실행 중 예외가 발생하면 `SagaCompensationFailedError`가 raise됩니다. 별도 에스컬레이션 핸들러(알림, 수동 개입 트리거 등)를 붙이려면 `SagaFlow.on_compensation_failure(handler)`를 사용합니다. 핸들러 실행 후에도 최종적으로 예외는 raise됩니다.

```python
async def notify_oncall(data: OrderSagaData) -> None:
    await alerting.send(f"Saga compensation failed: {data.order_id}")


flow = saga_flow(
    step(saga.create_order, compensate=saga.cancel_order),
    step(saga.process_payment, compensate=saga.refund_payment),
).on_compensation_failure(notify_oncall)
```

---

## 실행과 결과

### AbstractSaga.execute

`@Saga` 클래스의 표준 실행 진입점입니다. `flow()`를 호출하여 흐름을 구성하고 실행합니다. saga 이름은 클래스명으로 자동 설정되어 구조화 로그에 포함됩니다.

```python
result = await order_saga.execute(data)
```

### run_saga_flow

`AbstractSaga` 없이 직접 `SagaFlow`를 실행하려면 `run_saga_flow`를 사용합니다.

```python
from spakky.saga import run_saga_flow

result = await run_saga_flow(flow, data, saga_name="OrderSaga")
```

두 경로 모두 `SagaResult[T]`를 반환하며, 예외는 발생시키지 않습니다 (단, 보상 실패 시 `SagaCompensationFailedError`는 raise됩니다).

### SagaResult

| 필드 | 타입 | 설명 |
|------|------|------|
| `status` | `SagaStatus` | 사가 전체 상태 |
| `data` | `T` | 최종 사가 데이터 |
| `failed_step` | `str \| None` | 실패한 step 이름 |
| `error` | `Exception \| None` | 발생한 예외 |
| `history` | `tuple[StepRecord, ...]` | 각 step의 실행 기록 |
| `elapsed` | `timedelta` | 총 실행 시간 |

### SagaStatus

| 상태 | 설명 |
|------|------|
| `STARTED` | 사가 시작됨 (엔진 내부 전이용) |
| `RUNNING` | 실행 중 (엔진 내부 전이용) |
| `COMPENSATING` | 보상 실행 중 (엔진 내부 전이용) |
| `COMPLETED` | 모든 step 성공 |
| `FAILED` | 실패 (보상 수행 후) |
| `TIMED_OUT` | saga 전체 타임아웃 초과 |

### StepRecord / StepStatus

각 step의 실행 기록입니다.

| 필드 | 타입 | 설명 |
|------|------|------|
| `name` | `str` | step 이름 (함수 `__name__`) |
| `status` | `StepStatus` | `COMMITTED` / `FAILED` / `COMPENSATED` |
| `elapsed` | `timedelta` | step 실행 시간 |

---

## 구조화 로깅

사가 엔진은 실행 전 구간을 구조화 로그로 출력합니다. 로거 이름은 `spakky.saga.engine`입니다.

| 이벤트 | 로그 포맷 예시 | 레벨 |
|--------|---------------|------|
| saga 시작 | `[saga=OrderSaga status=started]` | INFO |
| step 시작 | `[saga=OrderSaga step=create_order status=started]` | INFO |
| step 성공 | `[saga=OrderSaga step=create_order status=completed elapsed=12ms]` | INFO |
| step 실패 | `[saga=OrderSaga step=process_payment status=failed error=TimeoutError]` | WARNING |
| step 재시도 | `[saga=OrderSaga step=process_payment status=retry attempt=2]` | INFO |
| 보상 실행 | `[saga=OrderSaga step=create_order status=compensating]` | INFO |
| 보상 성공 | `[saga=OrderSaga step=create_order status=compensated elapsed=8ms]` | INFO |
| saga 종료 | `[saga=OrderSaga status=COMPLETED elapsed=120ms]` | INFO |
| saga 예외 중단 | `[saga=OrderSaga status=aborted error=RuntimeError elapsed=15ms]` | WARNING |

`spakky-logging` 플러그인의 JSON 포맷을 사용하면 이 태그들이 구조화 필드로 파싱됩니다.

---

## 에러 계층

```
AbstractSpakkySagaError (ABC)
├── SagaFlowDefinitionError        — SagaFlow 정의 오류 (빈 흐름, parallel 최소 2개 미만, parallel 내부 on_error 위반 등)
├── SagaCompensationFailedError    — 보상 로직 실행 중 예외
├── SagaStepTimeoutError           — step 타임아웃 초과 (on_error 전략으로 라우팅)
├── SagaParallelMergeConflictError — 병렬 step 결과 병합 충돌 (예약)
└── SagaEngineNotConnectedError    — 엔진 미초기화 상태 실행 시도 (예약)
```

---

## 다음 단계

- [도메인 모델링](domain-modeling.md) — Aggregate Root, Entity, Domain Event
- [이벤트 시스템](events.md) — 도메인/통합 이벤트 발행
- [Transactional Outbox](outbox.md) — at-least-once 전달 보장
