"""AbstractSaga base class for saga definitions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from inspect import iscoroutinefunction
from typing import Generic

from spakky.saga.engine import run_saga_flow
from spakky.saga.flow import SagaDataT, SagaFlow, SagaStep
from spakky.saga.result import SagaResult


_FRAMEWORK_METHODS: frozenset[str] = frozenset({"flow", "execute"})


class _SagaStepDescriptor:
    """인스턴스 접근 시 bound method를 SagaStep으로 래핑하여 반환하는 디스크립터.

    AbstractSaga.__init_subclass__()에서 공개 비동기 메서드를
    이 디스크립터로 교체하여, 인스턴스에서 접근할 때 SagaStep 객체를
    반환하도록 한다. 이를 통해 연산자(>>, &, |) 사용이 가능해진다.
    """

    __slots__ = ("_fn",)

    def __init__(self, fn: object) -> None:
        self._fn = fn

    # fmt: off
    def __get__(
        self,
        obj: object | None,
        objtype: type | None = None,
    ) -> SagaStep[SagaDataT] | _SagaStepDescriptor:  # pyrefly: ignore - descriptor return type
        # fmt: on
        if obj is None:
            return self
        bound_method = self._fn.__get__(obj, objtype)  # type: ignore[union-attr] - fn is always a function with __get__
        return SagaStep(action=bound_method)


class AbstractSaga(ABC, Generic[SagaDataT]):
    """사가를 정의하는 제네릭 베이스 클래스.

    서브클래스는 flow()를 구현하여 사가 흐름을 선언적으로 정의한다.
    공개 비동기 메서드는 __init_subclass__()에 의해 SagaStep 디스크립터로
    자동 래핑되어 연산자(>>, &, |) 사용이 가능하다.

    Example:
        @Saga()
        class CreateOrderSaga(AbstractSaga[CreateOrderSagaData]):
            async def create_ticket(self, data):
                ...

            async def cancel_ticket(self, data):
                ...

            def flow(self) -> SagaFlow[CreateOrderSagaData]:
                return SagaFlow(items=(
                    self.create_ticket >> self.cancel_ticket,
                ))
    """

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        for name in list(vars(cls)):
            if name.startswith("_") or name in _FRAMEWORK_METHODS:
                continue
            value = vars(cls)[name]
            if callable(value) and iscoroutinefunction(value):
                setattr(cls, name, _SagaStepDescriptor(value))

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
        return await run_saga_flow(self.flow(), data)
