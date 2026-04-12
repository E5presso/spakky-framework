# 사가 오케스트레이션

`spakky-saga`는 분산 트랜잭션의 보상(compensation) 기반 롤백을 오케스트레이션합니다. `SagaFlow`와 `SagaStep`을 조합하여 비즈니스 프로세스를 선언적으로 모델링합니다.

---

## 동작 원리

1. `@Saga` 스테레오타입으로 사가 오케스트레이터 클래스를 선언
2. `SagaStep` 디스크립터로 각 단계의 action/compensation 핸들러를 등록
3. `>>` (순차), `&` (병렬), `|` (에러 전략) 연산자로 실행 흐름을 DSL로 조합
4. `run_saga_flow()`가 흐름을 실행하고 `SagaResult`를 반환
5. 단계 실패 시 `ErrorStrategy`에 따라 보상/재시도/스킵 처리

---

## 설정

`spakky-saga`는 `spakky`와 `spakky-domain`에 의존합니다.

```bash
pip install spakky-saga
```

---

## 사가 정의

### @Saga 스테레오타입

`@Saga`는 `@Pod`의 서브클래스입니다. 사가 오케스트레이터 클래스를 컨테이너에 등록합니다.

```python
from spakky.saga.stereotype import Saga
from spakky.saga.base import AbstractSaga
from spakky.saga.flow import SagaFlow

@Saga()
class OrderSaga(AbstractSaga[OrderSagaData]):
    async def create_order(self, data: OrderSagaData) -> OrderSagaData:
        ...

    async def cancel_order(self, data: OrderSagaData) -> None:
        ...

    async def reserve_stock(self, data: OrderSagaData) -> OrderSagaData:
        ...

    async def release_stock(self, data: OrderSagaData) -> None:
        ...

    async def process_payment(self, data: OrderSagaData) -> OrderSagaData:
        ...

    async def refund_payment(self, data: OrderSagaData) -> None:
        ...

    def flow(self) -> SagaFlow[OrderSagaData]:
        return SagaFlow(items=(
            self.create_order >> self.cancel_order,
            self.reserve_stock >> self.release_stock,
            self.process_payment >> self.refund_payment,
        ))
```

### AbstractSagaData

사가 데이터 모델은 `AbstractSagaData`를 상속합니다. `@immutable` + `AbstractDomainModel` 기반이므로 각 단계에서 읽기 전용으로 전달됩니다.

```python
from spakky.saga.data import AbstractSagaData
from spakky.core.common.mutability import immutable

@immutable
class OrderSagaData(AbstractSagaData):
    order_id: str
    customer_id: str
    total_amount: float
```

---

## SagaFlow DSL

### 흐름 연산자

| 연산자 | 의미 | 생성 타입 |
|--------|------|----------|
| `>>` | action + compensate 쌍 | `Transaction[T]` |
| `&` | 병렬 실행 | `Parallel[T]` |
| `\|` | 에러 전략 연결 | `SagaStep` + `ErrorStrategy` |

### 흐름 조합 예시

```python
from spakky.saga.flow import saga_flow, step, parallel
from spakky.saga.strategy import Compensate, Skip, Retry

# 순차 실행 (각 step을 saga_flow에 개별 인자로 전달)
flow = saga_flow(
    step(saga.create_order),
    step(saga.reserve_stock),
    step(saga.process_payment),
)

# 보상 함수 지정
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

# 에러 전략 적용
flow = saga_flow(
    step(saga.create_order, compensate=saga.cancel_order),
    parallel(
        step(saga.reserve_stock) | Skip(),
        step(saga.process_payment) | Retry(max_attempts=3),
    ),
)
```

---

## 에러 전략 (ErrorStrategy)

단계 실패 시 적용할 전략을 `|` 연산자로 지정합니다.

| 전략 | 설명 |
|------|------|
| `Compensate` | 보상 함수를 실행하여 롤백 (기본값) |
| `Skip` | 실패를 무시하고 다음 단계로 진행 |
| `Retry(max_attempts, backoff, then)` | 지정 횟수만큼 재시도 후 then 전략 적용 |

```python
from spakky.saga.strategy import (
    Compensate,
    Skip,
    Retry,
    ExponentialBackoff,
)

# 기본 보상
step(saga.reserve_stock, compensate=saga.release_stock) | Compensate()

# 3회 재시도 (실패 시 기본 Compensate)
step(saga.process_payment) | Retry(max_attempts=3)

# 지수 백오프 재시도 (기본 base=1.0초)
step(saga.send_notification) | Retry(
    max_attempts=5,
    backoff=ExponentialBackoff(base=2.0),
)

# 재시도 후 실패 무시
step(saga.log_analytics) | Retry(max_attempts=3, then=Skip())

# 실패 무시
step(saga.log_analytics) | Skip()
```

---

## 실행과 결과

### run_saga_flow

`run_saga_flow(flow, data)`로 사가를 실행합니다.

```python
from spakky.saga.engine import run_saga_flow

result = await run_saga_flow(flow, saga_data)
```

### SagaResult

실행 결과는 `SagaResult[T]`로 반환됩니다.

| 필드 | 타입 | 설명 |
|------|------|------|
| `status` | `SagaStatus` | 사가 전체 상태 |
| `data` | `T` | 최종 사가 데이터 |
| `failed_step` | `str \| None` | 실패한 단계 이름 |
| `error` | `Exception \| None` | 발생한 예외 |
| `history` | `tuple[StepRecord, ...]` | 각 단계의 실행 기록 |
| `elapsed` | `timedelta` | 총 실행 시간 |

### SagaStatus

| 상태 | 설명 |
|------|------|
| `STARTED` | 사가 시작됨 |
| `RUNNING` | 실행 중 |
| `COMPENSATING` | 보상 실행 중 |
| `COMPLETED` | 모든 단계 성공 |
| `FAILED` | 실패 (보상도 실패) |
| `TIMED_OUT` | 타임아웃 초과 |

### StepRecord

각 단계의 실행 기록입니다.

| 필드 | 타입 | 설명 |
|------|------|------|
| `name` | `str` | 단계 이름 |
| `status` | `StepStatus` | 단계 상태 (`COMMITTED`, `FAILED`, `COMPENSATED`) |
| `elapsed` | `timedelta` | 단계 실행 시간 |

---

## 에러 계층

```
AbstractSpakkySagaError (ABC)
├── SagaFlowDefinitionError       — SagaFlow 정의 오류
├── SagaCompensationFailedError   — 보상 로직 실행 중 예외
├── SagaParallelMergeConflictError — 병렬 단계 결과 병합 시 충돌
└── SagaEngineNotConnectedError   — 엔진 미초기화 상태에서 실행 시도
```

---

## 다음 단계

- [도메인 모델링](domain-modeling.md) — Aggregate Root, Entity, Domain Event
- [이벤트 시스템](events.md) — 도메인/통합 이벤트 발행
- [Transactional Outbox](outbox.md) — at-least-once 전달 보장
