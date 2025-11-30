from dataclasses import dataclass
from typing import Any

from spakky.aop.aspect import Aspect, AsyncAspect
from spakky.aop.interfaces.aspect import IAspect, IAsyncAspect
from spakky.aop.pointcut import Around
from spakky.aspects.logging import Logging
from spakky.core.annotation import FunctionAnnotation
from spakky.core.types import AsyncFunc, Func
from spakky.pod.annotations.order import Order
from spakky.stereotype.usecase import UseCase


@dataclass
class Dummy(FunctionAnnotation): ...


@dataclass
class AsyncDummy(FunctionAnnotation): ...


@Order(0)
@Aspect()
class DummyAdvisor(IAspect):
    @Around(Dummy.exists)
    def around(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:
        _annotation = Dummy.get(joinpoint)
        return joinpoint(*args, **kwargs)


@Order(0)
@AsyncAspect()
class AsyncDummyAdvisor(IAsyncAspect):
    @Around(AsyncDummy.exists)
    async def around_async(
        self, joinpoint: AsyncFunc, *args: Any, **kwargs: Any
    ) -> Any:
        _annotation = AsyncDummy.get(joinpoint)
        return await joinpoint(*args, **kwargs)


@UseCase()
class DummyUseCase:
    __name: str

    @property
    def name(self) -> str:
        return self.__name

    def __init__(self, name: str) -> None:
        self.__name = name

    @Logging()
    @Dummy()
    def execute(self) -> str:
        return "Hello, World!"


@UseCase()
class AsyncDummyUseCase:
    __name: str

    @property
    def name(self) -> str:
        return self.__name

    def __init__(self, name: str) -> None:
        self.__name = name

    @Logging()
    @AsyncDummy()
    async def execute(self) -> str:
        return "Hello, World!"
