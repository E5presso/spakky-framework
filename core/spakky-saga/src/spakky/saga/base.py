"""AbstractSaga base class + `@saga_step` 데코레이터.

사용자는 saga 메서드에 `@saga_step`을 명시적으로 적용한다. 데코레이터가
`_SagaStepDescriptor[SagaDataT]`를 반환하므로 타입체커는 클래스 속성 수준에서
명확한 타입을 인식하고, instance access 시 overload된 `__get__`이
`SagaStep[SagaDataT]`를 반환한다고 판단한다. 그 결과 `self.method >> ...`,
`self.method & ...`, `self.method | ...` 같은 연산자 표현이 타입 안전하게 작동한다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Awaitable, Callable, Generic, TypeVar, overload

from spakky.saga.engine import run_saga_flow
from spakky.saga.flow import SagaDataT, SagaFlow, SagaStep
from spakky.saga.result import SagaResult

_SelfT = TypeVar("_SelfT")


class _SagaStepDescriptor(Generic[SagaDataT]):
    """사가 메서드 descriptor. 인스턴스 접근 시 SagaStep을 반환한다.

    `@saga_step` 데코레이터가 적용된 메서드에 해당한다. 클래스 속성 수준에서는
    descriptor 객체 그대로 노출되고, 인스턴스에서 접근하면 `__get__`이
    bound method를 SagaStep으로 감싸 반환하여 연산자(>>, &, |) 사용이 가능해진다.
    """

    __slots__ = ("_fn",)

    def __init__(
        self,
        fn: Callable[..., Awaitable[SagaDataT | None]],
    ) -> None:
        self._fn = fn

    @overload
    def __get__(
        self,
        obj: None,
        objtype: type | None = None,
    ) -> _SagaStepDescriptor[SagaDataT]: ...
    @overload
    def __get__(
        self,
        obj: object,
        objtype: type | None = None,
    ) -> SagaStep[SagaDataT]: ...
    def __get__(
        self,
        obj: object | None,
        objtype: type | None = None,
    ) -> _SagaStepDescriptor[SagaDataT] | SagaStep[SagaDataT]:
        if obj is None:
            return self
        bound_method = self._fn.__get__(obj, objtype)
        return SagaStep(action=bound_method)


def saga_step(
    fn: Callable[[_SelfT, SagaDataT], Awaitable[SagaDataT | None]],
) -> _SagaStepDescriptor[SagaDataT]:
    """사가 step 메서드를 descriptor로 감싼다.

    데코레이트된 메서드에 instance-level로 접근하면 `SagaStep`이 반환되어
    `>>`, `&`, `|` 연산자로 Transaction/Parallel/에러 전략을 구성할 수 있다.

    Example:
        @Saga()
        class CreateOrderSaga(AbstractSaga[OrderData]):
            @saga_step
            async def issue_ticket(self, data: OrderData) -> OrderData: ...

            @saga_step
            async def cancel_ticket(self, data: OrderData) -> None: ...

            def flow(self) -> SagaFlow[OrderData]:
                return SagaFlow(items=(self.issue_ticket >> self.cancel_ticket,))

    Args:
        fn: 데코레이트할 async 메서드.

    Returns:
        `_SagaStepDescriptor[SagaDataT]`: 런타임 descriptor, 인스턴스 접근 시 `SagaStep`을 반환한다.
    """
    return _SagaStepDescriptor(fn)


class AbstractSaga(ABC, Generic[SagaDataT]):
    """사가를 정의하는 제네릭 베이스 클래스.

    서브클래스는 flow()를 구현하여 사가 흐름을 선언적으로 정의한다. 사가의
    step 역할을 하는 async 메서드에는 `@saga_step` 데코레이터를 붙여 연산자
    `>>`, `&`, `|` 사용을 타입 안전하게 활성화한다.

    Example:
        @Saga()
        class CreateOrderSaga(AbstractSaga[CreateOrderSagaData]):
            @saga_step
            async def create_ticket(self, data):
                ...

            @saga_step
            async def cancel_ticket(self, data):
                ...

            def flow(self) -> SagaFlow[CreateOrderSagaData]:
                return SagaFlow(items=(
                    self.create_ticket >> self.cancel_ticket,
                ))
    """

    @abstractmethod
    def flow(self) -> SagaFlow[SagaDataT]:
        """사가의 실행 흐름을 정의한다.

        Returns:
            SagaFlow[SagaDataT]: 사가 흐름 정의.
        """
        ...  # pragma: no branch - AbstractMethod only

    async def execute(self, data: SagaDataT) -> SagaResult[SagaDataT]:
        """사가를 실행한다.

        SagaFlow에 정의된 step들을 순차 실행하고, 실패 시
        compensate가 있는 step만 역순으로 보상을 실행한다.

        Args:
            data: 사가 비즈니스 데이터.

        Returns:
            SagaResult[SagaDataT]: 사가 실행 결과.

        Raises:
            SagaCompensationFailedError: 보상 실행 중 에러 발생
                (on_compensation_failure 미설정 시).
        """
        return await run_saga_flow(self.flow(), data, saga_name=type(self).__name__)
