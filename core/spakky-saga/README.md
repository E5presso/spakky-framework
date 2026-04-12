# spakky-saga

Distributed transaction saga orchestration for [Spakky Framework](https://github.com/E5presso/spakky-framework).

## Installation

```bash
pip install spakky-saga
```

## Features

- **`@Saga` stereotype**: Marks saga orchestrator classes (extends `@Pod`)
- **`AbstractSaga[SagaDataT]`**: Generic base class with `flow()` abstract method and `execute()` entry point
- **`@saga_step` decorator**: Typed descriptor that enables `>>`, `&`, `|` operators on instance methods
- **Flow DSL**: Declarative composition via operators or builder functions (`saga_flow`, `step`, `parallel`)
- **Error strategies**: `Compensate` (default), `Skip`, `Retry(max_attempts, backoff, then)` with `ExponentialBackoff`
- **Timeouts**: Per-step (`timeout=`) and per-saga (`SagaFlow.timeout()`)
- **Parallel execution**: `asyncio.gather` based groups (`&` operator / `parallel()`)
- **Compensation**: Automatic reverse-order rollback of committed steps on failure
- **`SagaResult[T]`**: Non-throwing result with `status`, `data`, `failed_step`, `error`, `history`, `elapsed`
- **Structured logging**: `[saga=... step=... status=... elapsed=...ms]` format

## Quick Start

### Define Saga Data

```python
from spakky.saga import AbstractSagaData


class OrderSagaData(AbstractSagaData):
    order_id: int
    customer_id: int
    ticket_id: int | None = None
```

### Define a Saga

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

### Execute

```python
result = await saga.execute(OrderSagaData(order_id=1, customer_id=42))
if result.status is SagaStatus.COMPLETED:
    ...
```

### Builder Function Alternative

```python
from spakky.saga import Retry, parallel, saga_flow, step


flow = saga_flow(
    step(issue_ticket_fn, compensate=cancel_ticket_fn),
    parallel(reserve_stock_fn, charge_payment_fn),
    step(confirm_order_fn, on_error=Retry(max_attempts=3)),
)
```

## Flow Operators

| Operator | Meaning | Result Type |
|----------|---------|-------------|
| `>>` | Bind compensate function | `Transaction[T]` |
| `&` | Parallel execution | `Parallel[T]` |
| `\|` | Attach error strategy | Same as LHS + `on_error` |

## Error Strategies

| Strategy | Signature | Description |
|----------|-----------|-------------|
| `Compensate()` | (default) | Trigger reverse-order compensation |
| `Skip()` | — | Ignore failure and continue |
| `Retry(max_attempts, backoff, then)` | `Retry(3, ExponentialBackoff(1.0), Compensate())` | Retry N times, then apply `then` strategy |
| `ExponentialBackoff(base=1.0)` | — | `base * 2^(attempt-1)` delay between retries |

## API Reference

### Stereotype / Base

| Symbol | Description |
|--------|-------------|
| `@Saga()` | Stereotype for saga orchestrator classes (extends `@Pod`) |
| `AbstractSaga[SagaDataT]` | ABC base with `flow()` abstract method and `execute()` |
| `@saga_step` | Descriptor decorator enabling `>>`, `&`, `\|` operators |
| `AbstractSagaData` | Base data model (`@immutable` + `AbstractDomainModel`, auto-generates `saga_id: UUID`) |

### Flow Types

| Symbol | Description |
|--------|-------------|
| `SagaFlow[T]` | Top-level flow definition (`items`, `saga_timeout`, `compensation_failure_handler`) |
| `SagaStep[T]` | Single action without compensation |
| `Transaction[T]` | Action + compensate pair |
| `Parallel[T]` | Concurrent group of steps/transactions |
| `FlowItem[T]` | Union of flow-composable items |
| `ActionFn[T]` / `CompensateFn[T]` | Type aliases for action / compensate callables |
| `SagaDataT` | TypeVar bound to `AbstractSagaData` |

### Builders

| Function | Description |
|----------|-------------|
| `saga_flow(*items)` | Construct a `SagaFlow` from sequential items |
| `step(action, *, compensate=, on_error=, timeout=)` | Build `SagaStep` or `Transaction` |
| `parallel(*items)` | Build a `Parallel` group (requires ≥ 2 items) |

### Execution

| Symbol | Description |
|--------|-------------|
| `run_saga_flow(flow, data, *, saga_name=)` | Execute a flow; returns `SagaResult` |
| `AbstractSaga.execute(data)` | Thin wrapper over `run_saga_flow` using `type(self).__name__` |

### Result Types

| Symbol | Description |
|--------|-------------|
| `SagaResult[T]` | `status`, `data`, `failed_step`, `error`, `history`, `elapsed` |
| `StepRecord` | `name`, `status`, `elapsed` — per-step execution record |
| `StepStatus` | `COMMITTED`, `FAILED`, `COMPENSATED` |
| `SagaStatus` | `STARTED`, `RUNNING`, `COMPENSATING`, `COMPLETED`, `FAILED`, `TIMED_OUT` |

### Errors

| Error | Description |
|-------|-------------|
| `AbstractSpakkySagaError` | ABC base for all saga errors |
| `SagaFlowDefinitionError` | Invalid saga flow definition (static validation) |
| `SagaCompensationFailedError` | Compensation failed during rollback |
| `SagaStepTimeoutError` | Raised internally when a step exceeds its timeout (routed through `on_error`) |
| `SagaParallelMergeConflictError` | Parallel steps modified the same field during data merge |
| `SagaEngineNotConnectedError` | `execute()` called before the saga engine is connected |

## Related

- [ADR-0007](../../docs/adr/0007-spakky-saga-plan.md) — Architecture decision record
- `spakky-domain` — provides `AbstractDomainModel` (parent of `AbstractSagaData`)

## License

MIT License
