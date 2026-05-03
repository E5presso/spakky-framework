# spakky-saga

[Spakky Framework](https://github.com/E5presso/spakky-framework)를 위한 분산 트랜잭션 사가 오케스트레이션입니다.

## 설치

```bash
pip install spakky-saga
```

## 주요 기능

- **`@Saga` stereotype**: saga orchestrator class를 표시합니다(`@Pod` 확장).
- **`AbstractSaga[SagaDataT]`**: `flow()` 추상 메서드와 `execute()` entry point를 가진 generic base class입니다.
- **`@saga_step` decorator**: instance method에서 `>>`, `&`, `|` 연산자를 활성화하는 typed descriptor입니다.
- **Flow DSL**: 연산자 또는 builder 함수(`saga_flow`, `step`, `parallel`)로 선언적 구성
- **Error strategy**: `Compensate`(기본값), `Skip`, `ExponentialBackoff`을 포함한 `Retry(max_attempts, backoff, then)`을 제공합니다.
- **Timeout**: step별 `timeout=`과 saga별 `SagaFlow.timeout()` 지원
- **병렬 실행**: `asyncio.gather` 기반 group(`&` operator / `parallel()`)
- **보상**: 실패 시 commit된 step을 역순으로 자동 rollback
- **`SagaResult[T]`**: `status`, `data`, `failed_step`, `error`, `history`, `elapsed`를 담는 non-throwing result
- **구조화 로깅**: `[saga=... step=... status=... elapsed=...ms]` format

## 빠른 시작

### SagaData 정의

```python
from spakky.saga import AbstractSagaData


class OrderSagaData(AbstractSagaData):
    order_id: int
    customer_id: int
    ticket_id: int | None = None
```

### Saga 정의

```python
from spakky.saga import AbstractSaga, Saga, SagaFlow, saga_step


@Saga()
class CreateOrderSaga(AbstractSaga[OrderSagaData]):
    @saga_step
    async def issue_ticket(self, data: OrderSagaData) -> OrderSagaData:
        ...

    @saga_step
    async def cancel_ticket(self, data: OrderSagaData) -> None:
        ...

    @saga_step
    async def reserve_stock(self, data: OrderSagaData) -> OrderSagaData:
        ...

    def flow(self) -> SagaFlow[OrderSagaData]:
        return SagaFlow(
            items=(
                self.issue_ticket >> self.cancel_ticket,  # Transaction
                self.reserve_stock,                        # SagaStep (no compensation)
            )
        )
```

### 실행

```python
result = await saga.execute(OrderSagaData(order_id=1, customer_id=42))
if result.status is SagaStatus.COMPLETED:
    ...
```

### Builder 함수 대안

```python
from spakky.saga import Retry, parallel, saga_flow, step


flow = saga_flow(
    step(issue_ticket_fn, compensate=cancel_ticket_fn),
    parallel(reserve_stock_fn, charge_payment_fn),
    step(confirm_order_fn, on_error=Retry(max_attempts=3)),
)
```

## Flow 연산자

| 연산자 | 의미 | 결과 타입 |
|----------|---------|-------------|
| `>>` | compensate 함수 바인딩 | `Transaction[T]` |
| `&` | 병렬 실행 | `Parallel[T]` |
| `\|` | 에러 전략 부착 | 좌변과 동일한 타입 + `on_error` |

## Error Strategy

| Strategy | Signature | 설명 |
|----------|-----------|-------------|
| `Compensate()` | (기본값) | 역순 compensation 실행 |
| `Skip()` | — | 실패를 무시하고 계속 진행 |
| `Retry(max_attempts, backoff, then)` | `Retry(3, ExponentialBackoff(1.0), Compensate())` | N회 재시도 후 `then` 전략 적용 |
| `ExponentialBackoff(base=1.0)` | — | retry 사이에 `base * 2^(attempt-1)` delay 적용 |

## API 레퍼런스

### Stereotype / Base

| 기호 | 설명 |
|--------|-------------|
| `@Saga()` | saga orchestrator class용 stereotype(`@Pod` 확장) |
| `AbstractSaga[SagaDataT]` | `flow()` 추상 메서드와 `execute()`를 가진 ABC 기반 클래스 |
| `@saga_step` | `>>`, `&`, `|` 연산자를 활성화하는 descriptor decorator |
| `AbstractSagaData` | base data model(`@immutable` + `AbstractDomainModel`, `saga_id: UUID` 자동 생성) |

### Flow 타입

| 기호 | 설명 |
|--------|-------------|
| `SagaFlow[T]` | 최상위 flow 정의(`items`, `saga_timeout`, `compensation_failure_handler`) |
| `SagaStep[T]` | compensation 없는 단일 action |
| `Transaction[T]` | action + compensate 쌍 |
| `Parallel[T]` | step/transaction 동시 실행 그룹 |
| `FlowItem[T]` | flow 구성 가능 item의 union |
| `ActionFn[T]` / `CompensateFn[T]` | action / compensate callable용 type alias |
| `SagaDataT` | `AbstractSagaData`에 bound된 TypeVar |

### Builder

| 함수 | 설명 |
|----------|-------------|
| `saga_flow(*items)` | 순차 item으로 `SagaFlow` 생성 |
| `step(action, *, compensate=, on_error=, timeout=)` | `SagaStep` 또는 `Transaction` 생성 |
| `parallel(*items)` | `Parallel` group 생성(최소 2개 item 필요) |

### 실행

| 기호 | 설명 |
|--------|-------------|
| `run_saga_flow(flow, data, *, saga_name=)` | flow 실행 후 `SagaResult` 반환 |
| `AbstractSaga.execute(data)` | `type(self).__name__`을 사용하는 `run_saga_flow` 얇은 wrapper |

### Result 타입

| 기호 | 설명 |
|--------|-------------|
| `SagaResult[T]` | `status`, `data`, `failed_step`, `error`, `history`, `elapsed` |
| `StepRecord` | `name`, `status`, `elapsed` — per-step execution record |
| `StepStatus` | `COMMITTED`, `FAILED`, `COMPENSATED` |
| `SagaStatus` | `STARTED`, `RUNNING`, `COMPENSATING`, `COMPLETED`, `FAILED`, `TIMED_OUT` |

### 에러

| 에러 | 설명 |
|-------|-------------|
| `AbstractSpakkySagaError` | 모든 saga error의 ABC 기반 클래스 |
| `SagaFlowDefinitionError` | 유효하지 않은 saga flow 정의(정적 검증) |
| `SagaCompensationFailedError` | rollback 중 compensation 실패 |
| `SagaStepTimeoutError` | step timeout 초과 시 내부에서 발생(`on_error`로 라우팅) |
| `SagaParallelMergeConflictError` | 병렬 step이 data merge 중 같은 필드 변경 |
| `SagaEngineNotConnectedError` | saga engine 연결 전에 `execute()`가 호출됨 |

## 관련 문서

- [ADR-0007](../../docs/adr/0007-spakky-saga-plan.md) — architecture decision record
- `spakky-domain` — `AbstractSagaData`의 부모인 `AbstractDomainModel` 제공

## 라이선스

MIT License
