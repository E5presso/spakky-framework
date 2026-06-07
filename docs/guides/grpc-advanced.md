# gRPC 심화

> `spakky-grpc`로 Saga 결과를 gRPC 상태 코드에 매핑하고, 서비스 계약을 운영 친화적으로 고정하는 방법을 다룹니다.

이 문서는 [gRPC 통합](grpc.md)을 읽은 뒤 확인하는 심화 가이드입니다. 기본 문서가 code-first 서비스 정의와 서버 부트스트랩에 집중한다면, 여기서는 Saga 같은 긴 비즈니스 흐름을 RPC 경계에서 어떻게 응답으로 바꿀지 다룹니다.

## gRPC Controller에서 Saga 호출

gRPC Controller도 다른 Controller와 동일하게 Saga Pod를 생성자 주입으로 받습니다. `AbstractSaga.execute(data)`는 `SagaResult[T]`를 반환하므로, RPC 메서드에서는 `SagaStatus`를 보고 응답 메시지 또는 `AbstractGrpcStatusError` 서브클래스로 분기합니다. `ErrorHandlingInterceptor`가 이 에러를 잡아 선언된 gRPC `StatusCode`로 변환합니다.

```python
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel
from spakky.core.common.error import AbstractSpakkyFrameworkError
from spakky.plugins.grpc.annotations.field import ProtoField
from spakky.plugins.grpc.decorators.rpc import rpc
from spakky.plugins.grpc.error import (
    AbstractGrpcStatusError,
    FailedPrecondition,
    InternalError,
    InvalidArgument,
    Unavailable,
)
from spakky.plugins.grpc.stereotypes.grpc_controller import GrpcController
from spakky.saga import SagaStatus


class CreateOrderRequest(BaseModel):
    customer_id: Annotated[str, ProtoField(number=1)]
    total_amount: Annotated[float, ProtoField(number=2)]


class CreateOrderReply(BaseModel):
    order_id: Annotated[str, ProtoField(number=1)]
    status: Annotated[str, ProtoField(number=2)]


class OrderBusinessRuleViolation(AbstractSpakkyFrameworkError):
    """Application error raised by an expected order-domain rule."""

    message = "Order cannot be created in the current state"


class OrderDependencyUnavailable(AbstractSpakkyFrameworkError):
    """Application error raised when inventory/payment dependencies fail."""

    message = "Order dependency is unavailable"


def map_saga_failure(error: Exception | None) -> AbstractGrpcStatusError:
    if isinstance(error, OrderBusinessRuleViolation):
        return FailedPrecondition()
    if isinstance(error, OrderDependencyUnavailable):
        return Unavailable()
    return InternalError()


def require_created_order_id(data: OrderSagaData) -> UUID:
    if data.order_id is None:
        raise InternalError()
    return data.order_id


@GrpcController(package="example.order", service_name="OrderService")
class OrderGrpcController:
    def __init__(self, order_saga: OrderSaga) -> None:
        self._order_saga = order_saga

    @rpc()
    async def create_order(self, request: CreateOrderRequest) -> CreateOrderReply:
        try:
            customer_id = UUID(request.customer_id)
        except ValueError as error:
            raise InvalidArgument() from error

        result = await self._order_saga.execute(
            OrderSagaData(
                customer_id=customer_id,
                total_amount=request.total_amount,
            )
        )

        match result.status:
            case SagaStatus.COMPLETED:
                return CreateOrderReply(
                    order_id=str(require_created_order_id(result.data)),
                    status=result.status.value,
                )
            case SagaStatus.FAILED:
                raise map_saga_failure(result.error)
            case SagaStatus.TIMED_OUT:
                raise Unavailable()
            case _:
                raise InternalError()
```

상태 매핑은 서비스 계약에 맞게 고정합니다.

| `SagaStatus` | gRPC 에러 | 의미 |
|--------------|-----------|------|
| `COMPLETED` | 정상 응답 | 모든 step이 성공했고 최종 `SagaData`로 응답 생성 |
| `FAILED` | 분류 후 매핑 | `result.error`가 기대된 도메인 실패이면 `FailedPrecondition`, 외부 의존성 장애이면 `Unavailable`, 그 외는 `InternalError` |
| `TIMED_OUT` | `Unavailable` | 외부 결제·재고 등 일시 장애로 재시도 가능한 실패 |
| 그 외 | `InternalError` | `execute()` 반환 시점에 관찰되면 안 되는 내부 상태 |

`SagaStatus.FAILED`는 step에서 발생한 임의의 예외를 `result.error`에 담을 수 있으므로, 모든 실패를 `FailedPrecondition`으로 취급하지 않습니다. `InvalidArgument`, `NotFound`, `AlreadyExists` 같은 더 구체적인 에러를 쓰려면 Saga step 내부의 UseCase가 반환하거나 발생시킨 애플리케이션 에러를 Controller 경계에서 분류한 뒤 해당 `AbstractGrpcStatusError` 서브클래스를 raise합니다. 이 에러 클래스들은 `plugins/spakky-grpc/src/spakky/plugins/grpc/error.py`에 정의되어 있으며, 인터셉터는 `error.message`를 gRPC detail로 사용합니다.

## 더 볼 곳

- [gRPC 통합](grpc.md): code-first 서비스 정의와 서버 부트스트랩을 다룹니다.
- [사가 오케스트레이션](saga.md): Saga의 기본 흐름과 보상 모델을 설명합니다.
- [사가 심화](saga-advanced.md): DSL, 에러 전략, 타임아웃, Semantic Lock을 다룹니다.
