# spakky-saga

Distributed transaction saga orchestration for [Spakky Framework](https://github.com/E5presso/spakky-framework).

## Installation

```bash
pip install spakky-saga
```

## Planned Features

- **Flow builder pattern**: Declarative saga definition with `saga_flow()` and `step()`
- **Operator syntax sugar**: `>>` (compensate), `&` (parallel), `|` (error strategy)
- **Error strategies**: `Compensate`, `Skip`, `Retry(max_attempts, then=)`
- **Timeout support**: Per-step and per-saga timeout
- **`SagaResult[T]`**: Non-throwing result object with status, data, and execution history

## Errors

| Error | Description |
|-------|-------------|
| `SagaFlowDefinitionError` | Invalid saga flow definition (static validation) |
| `SagaCompensationFailedError` | Compensation fails during saga rollback |
| `SagaParallelMergeConflictError` | Parallel steps modify the same field during data merge |

## Related

- [ADR-0007](../../docs/adr/0007-spakky-saga-plan.md) — Architecture decision record

## License

MIT License
