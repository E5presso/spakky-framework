import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import pytest

from spakky.core.aop.aspect import Aspect, AsyncAspect
from spakky.core.aop.interfaces.aspect import IAspect, IAsyncAspect
from spakky.core.aop.pointcut import After, AfterRaising, AfterReturning, Around, Before
from spakky.core.application.application_context import ApplicationContext
from spakky.core.common.annotation import FunctionAnnotation
from spakky.core.common.types import AnyT, AsyncFunc, Func
from spakky.core.pod.annotations.pod import Pod


def test_aop_with_no_implementations() -> None:
    """Aspect 구현체가 없을 때 원래 메서드가 정상 동작함을 검증한다."""
    logs: list[str] = []

    @dataclass
    class Log(FunctionAnnotation): ...

    @Aspect()
    class LogAdvisor(IAspect): ...

    @Pod()
    class EchoService:
        @Log()
        def echo(self, message: str) -> str:
            return message

    context: ApplicationContext = ApplicationContext()

    console = logging.StreamHandler()
    console.setLevel(level=logging.DEBUG)
    console.setFormatter(logging.Formatter("[%(levelname)s][%(asctime)s]: %(message)s"))
    logger: logging.Logger = logging.getLogger("debug")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(console)

    context.add(EchoService)
    context.add(LogAdvisor)

    context.start()

    service: EchoService = context.get(type_=EchoService)
    assert service.echo(message="Hello World!") == "Hello World!"
    assert len(logs) == 0


def test_aop() -> None:
    """AOP의 Before, AfterRaising, AfterReturning, After, Around advice가 올바른 순서로 실행됨을 검증한다."""
    logs: list[str] = []

    @dataclass
    class Log(FunctionAnnotation): ...

    @Aspect()
    class LogAdvisor(IAspect):
        @Before(Log.exists)
        def before(self, *args: Any, **kwargs: Any) -> None:
            nonlocal logs
            logs.append(f"before {args}, {kwargs}")

        @AfterRaising(Log.exists)
        def after_raising(self, error: Exception) -> None:
            nonlocal logs
            logs.append(f"after_raising {error}")

        @AfterReturning(Log.exists)
        def after_returning(self, result: Any) -> None:
            nonlocal logs
            logs.append(f"after_returning {result}")

        @After(Log.exists)
        def after(self) -> None:
            nonlocal logs
            logs.append("after")

        @Around(Log.exists)
        def around(
            self,
            joinpoint: Func,
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            nonlocal logs
            try:
                result = joinpoint(*args, **kwargs)
                logs.append(f"around {args}, {kwargs} {result}")
                return result
            except Exception as e:
                logs.append(f"around {args}, {kwargs} {e}")
                raise

    @Pod()
    class EchoService:
        @Log()
        def echo(self, message: str) -> str:
            return message

    context: ApplicationContext = ApplicationContext()

    context.add(EchoService)
    context.add(LogAdvisor)

    context.start()

    service: EchoService = context.get(type_=EchoService)
    assert service.echo(message="Hello World!") == "Hello World!"
    assert logs[0] == "before (), {'message': 'Hello World!'}"
    assert logs[1] == "around (), {'message': 'Hello World!'} Hello World!"
    assert logs[2] == "after_returning Hello World!"
    assert logs[3] == "after"


def test_aop_with_another_pod() -> None:
    """Log 어노테이션이 없는 Pod에는 Aspect가 적용되지 않음을 검증한다."""
    logs: list[str] = []

    @dataclass
    class Log(FunctionAnnotation): ...

    @Aspect()
    class LogAdvisor(IAspect):
        @Before(Log.exists)
        def before(self, *args: Any, **kwargs: Any) -> None:
            return super().before(*args, **kwargs)

        @AfterReturning(Log.exists)
        def after_returning(self, result: Any) -> None:
            return super().after_returning(result)

        @AfterRaising(Log.exists)
        def after_raising(self, error: Exception) -> None:
            return super().after_raising(error)

        @After(Log.exists)
        def after(self) -> None:
            return super().after()

        @Around(Log.exists)
        def around(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:
            return super().around(joinpoint, *args, **kwargs)

    @Pod()
    class EchoService:
        @Log()
        def echo(self, message: str) -> str:
            return message

    @Pod()
    class AnotherService:
        def echo(self, message: str) -> str:
            return message

    context: ApplicationContext = ApplicationContext()

    context.add(EchoService)
    context.add(AnotherService)
    context.add(LogAdvisor)

    context.start()

    assert context.get(type_=EchoService).echo(message="Hello World!") == "Hello World!"
    assert (
        context.get(type_=AnotherService).echo(message="Hello World!") == "Hello World!"
    )
    assert len(logs) == 0

    assert dir(context.get(type_=EchoService)) == dir(EchoService())


def test_aop_with_no_implementations_raise_error() -> None:
    """Aspect 구현체 없이 메서드에서 예외 발생 시 정상적으로 전파됨을 검증한다."""
    logs: list[str] = []

    @dataclass
    class Log(FunctionAnnotation): ...

    @Aspect()
    class LogAdvisor(IAspect): ...

    @Pod()
    class EchoService:
        @Log()
        def echo(self, message: str) -> str:
            raise RuntimeError

    context: ApplicationContext = ApplicationContext()

    context.add(EchoService)
    context.add(LogAdvisor)

    context.start()

    service: EchoService = context.get(type_=EchoService)
    with pytest.raises(RuntimeError):
        assert service.echo(message="Hello World!") == "Hello World!"
    assert len(logs) == 0


def test_aop_with_implementations_raise_error() -> None:
    """메서드에서 예외 발생 시 AfterRaising advice가 호출됨을 검증한다."""
    logs: list[str] = []

    @dataclass
    class Log(FunctionAnnotation): ...

    @Aspect()
    class LogAdvisor(IAspect):
        @AfterRaising(Log.exists)
        def after_raising(self, error: Exception) -> None:
            nonlocal logs
            logs.append(f"after_raising {type(error).__name__}")
            return super().after_raising(error)

    @Pod()
    class EchoService:
        @Log()
        def echo(self, message: str) -> str:
            raise RuntimeError

    context: ApplicationContext = ApplicationContext()

    context.add(EchoService)
    context.add(LogAdvisor)

    context.start()

    service: EchoService = context.get(type_=EchoService)
    with pytest.raises(RuntimeError):
        assert service.echo(message="Hello World!") == "Hello World!"

    assert logs[0] == "after_raising RuntimeError"


def test_aop_raise_error() -> None:
    """메서드 예외 발생 시 모든 advice(Before, Around, AfterRaising, After)가 올바른 순서로 동작함을 검증한다."""
    logs: list[str] = []

    @dataclass
    class Log(FunctionAnnotation): ...

    @Aspect()
    class LogAdvisor(IAspect):
        @Before(Log.exists)
        def before(self, *args: Any, **kwargs: Any) -> None:
            nonlocal logs
            logs.append(f"before {args}, {kwargs}")

        @AfterRaising(Log.exists)
        def after_raising(self, error: Exception) -> None:
            nonlocal logs
            logs.append(f"after_raising {error}")

        @AfterReturning(Log.exists)
        def after_returning(self, result: Any) -> None:
            nonlocal logs
            logs.append(f"after_returning {result}")

        @After(Log.exists)
        def after(self) -> None:
            nonlocal logs
            logs.append("after")

        @Around(Log.exists)
        def around(
            self,
            joinpoint: Func,
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            nonlocal logs
            try:
                result = joinpoint(*args, **kwargs)
            except Exception as e:
                logs.append(f"around {args}, {kwargs} {e}")
                raise
            else:
                logs.append(f"around {args}, {kwargs} {result}")
                return result

    @Pod()
    class EchoService:
        @Log()
        def echo(self, message: str) -> str:
            raise RuntimeError

    context: ApplicationContext = ApplicationContext()

    context.add(EchoService)
    context.add(LogAdvisor)

    context.start()

    service: EchoService = context.get(type_=EchoService)
    with pytest.raises(RuntimeError):
        assert service.echo(message="Hello World!") == "Hello World!"
    assert logs[0] == "before (), {'message': 'Hello World!'}"
    assert logs[1] == "around (), {'message': 'Hello World!'} "
    assert logs[2] == "after_raising "
    assert logs[3] == "after"


def test_aop_that_does_not_have_any_aspects() -> None:
    """Aspect가 정의되지 않은 상태에서도 메서드가 정상 동작함을 검증한다."""
    logs: list[str] = []

    @dataclass
    class Log(FunctionAnnotation): ...

    @Aspect()
    class LogAdvisor(IAspect): ...

    @Pod()
    class EchoService:
        @Log()
        def echo(self, message: str) -> str:
            return message

    context: ApplicationContext = ApplicationContext()

    context.add(EchoService)
    context.add(LogAdvisor)

    context.start()

    service: EchoService = context.get(type_=EchoService)
    assert service.echo(message="Hello World!") == "Hello World!"
    assert len(logs) == 0


def test_aop_with_no_method() -> None:
    """@Log 어노테이션이 적용된 메서드가 없는 Pod에서 속성 접근이 정상 동작함을 검증한다."""
    logs: list[str] = []

    @dataclass
    class Log(FunctionAnnotation): ...

    @Aspect()
    class LogAdvisor(IAspect):
        @Before(Log.exists)
        def before(self, *args: Any, **kwargs: Any) -> None:
            nonlocal logs
            logs.append(f"before {args}, {kwargs}")

        @AfterRaising(Log.exists)
        def after_raising(self, error: Exception) -> None:
            nonlocal logs
            logs.append(f"after_raising {error}")

        @AfterReturning(Log.exists)
        def after_returning(self, result: Any) -> None:
            nonlocal logs
            logs.append(f"after_returning {result}")

        @After(Log.exists)
        def after(self) -> None:
            nonlocal logs
            logs.append("after")

        @Around(Log.exists)
        def around(
            self,
            joinpoint: Func,
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            nonlocal logs
            try:
                result = joinpoint(*args, **kwargs)
            except Exception as e:
                logs.append(f"around {args}, {kwargs} {e}")
                raise
            else:
                logs.append(f"around {args}, {kwargs} {result}")
                return result

    @Pod()
    class EchoService:
        message = "Hello World!"

    context: ApplicationContext = ApplicationContext()

    context.add(EchoService)
    context.add(LogAdvisor)

    context.start()

    service: EchoService = context.get(type_=EchoService)
    assert service.message == "Hello World!"
    assert len(logs) == 0


def test_aop_with_dependencies() -> None:
    """의존성 주입을 사용하는 Pod에 AOP가 정상 적용됨을 검증한다."""
    logs: list[str] = []

    @dataclass
    class Log(FunctionAnnotation): ...

    @Aspect()
    class LogAdvisor(IAspect):
        @Before(Log.exists)
        def before(self, *args: Any, **kwargs: Any) -> None:
            nonlocal logs
            logs.append(f"before {args}, {kwargs}")

        @AfterRaising(Log.exists)
        def after_raising(self, error: Exception) -> None:
            nonlocal logs
            logs.append(f"after_raising {error}")

        @AfterReturning(Log.exists)
        def after_returning(self, result: Any) -> None:
            nonlocal logs
            logs.append(f"after_returning {result}")

        @After(Log.exists)
        def after(self) -> None:
            nonlocal logs
            logs.append("after")

        @Around(Log.exists)
        def around(
            self,
            joinpoint: Func,
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            nonlocal logs
            try:
                result = joinpoint(*args, **kwargs)
            except Exception as e:
                logs.append(f"around {args}, {kwargs} {e}")
                raise
            else:
                logs.append(f"around {args}, {kwargs} {result}")
                return result

    @Pod()
    class EchoService:
        message: str

        def __init__(self, message: str) -> None:
            self.message = message

        @Log()
        def echo(self) -> str:
            return self.message

    context: ApplicationContext = ApplicationContext()

    @Pod(name="message")
    def get_message() -> str:
        return "Hello World!"

    context.add(get_message)
    context.add(EchoService)
    context.add(LogAdvisor)

    context.start()

    service: EchoService = context.get(type_=EchoService)
    assert service.message == "Hello World!"
    assert service.echo() == "Hello World!"
    assert logs[0] == "before (), {}"
    assert logs[1] == "around (), {} Hello World!"
    assert logs[2] == "after_returning Hello World!"
    assert logs[3] == "after"


@pytest.mark.asyncio
async def test_async_aop_with_no_implementations() -> None:
    """AsyncAspect 구현체가 없을 때 비동기 메서드가 정상 동작함을 검증한다."""
    logs: list[str] = []

    @dataclass
    class AsyncLog(FunctionAnnotation):
        def __call__(
            self, obj: Callable[..., Awaitable[AnyT]]
        ) -> Callable[..., Awaitable[AnyT]]:
            return super().__call__(obj)

    @AsyncAspect()
    class AsyncLogAdvisor(IAsyncAspect): ...

    @Pod()
    class EchoService:
        @AsyncLog()
        async def echo(self, message: str) -> str:
            return message

    context: ApplicationContext = ApplicationContext()

    context.add(EchoService)
    context.add(AsyncLogAdvisor)

    context.start()

    service: EchoService = context.get(type_=EchoService)
    assert await service.echo(message="Hello World!") == "Hello World!"
    assert len(logs) == 0


@pytest.mark.asyncio
async def test_async_aop() -> None:
    """비동기 AOP의 Before, AfterRaising, AfterReturning, After, Around advice가 올바른 순서로 실행됨을 검증한다."""
    logs: list[str] = []

    @dataclass
    class AsyncLog(FunctionAnnotation):
        def __call__(
            self, obj: Callable[..., Awaitable[AnyT]]
        ) -> Callable[..., Awaitable[AnyT]]:
            return super().__call__(obj)

    @AsyncAspect()
    class AsyncLogAdvisor(IAsyncAspect):
        @Before(AsyncLog.exists)
        async def before_async(self, *args: Any, **kwargs: Any) -> None:
            nonlocal logs
            logs.append(f"before {args}, {kwargs}")

        @AfterRaising(AsyncLog.exists)
        async def after_raising_async(self, error: Exception) -> None:
            nonlocal logs
            logs.append(f"after_raising {error}")

        @AfterReturning(AsyncLog.exists)
        async def after_returning_async(self, result: Any) -> None:
            nonlocal logs
            logs.append(f"after_returning {result}")

        @After(AsyncLog.exists)
        async def after_async(self) -> None:
            nonlocal logs
            logs.append("after")

        @Around(AsyncLog.exists)
        async def around_async(
            self,
            joinpoint: AsyncFunc,
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            nonlocal logs
            try:
                result = await joinpoint(*args, **kwargs)
            except Exception as e:
                logs.append(f"around {args}, {kwargs} {e}")
                raise
            else:
                logs.append(f"around {args}, {kwargs} {result}")
                return result

    @Pod()
    class EchoService:
        @AsyncLog()
        async def echo(self, message: str) -> str:
            return message

    context: ApplicationContext = ApplicationContext()

    context.add(EchoService)
    context.add(AsyncLogAdvisor)

    context.start()

    service: EchoService = context.get(type_=EchoService)
    assert await service.echo(message="Hello World!") == "Hello World!"
    assert logs[0] == "before (), {'message': 'Hello World!'}"
    assert logs[1] == "around (), {'message': 'Hello World!'} Hello World!"
    assert logs[2] == "after_returning Hello World!"
    assert logs[3] == "after"


@pytest.mark.asyncio
async def test_async_aop_with_another_pod() -> None:
    """AsyncLog 어노테이션이 없는 Pod에는 AsyncAspect가 적용되지 않음을 검증한다."""
    logs: list[str] = []

    @dataclass
    class AsyncLog(FunctionAnnotation):
        def __call__(
            self, obj: Callable[..., Awaitable[AnyT]]
        ) -> Callable[..., Awaitable[AnyT]]:
            return super().__call__(obj)

    @AsyncAspect()
    class AsyncLogAdvisor(IAsyncAspect):
        @Before(AsyncLog.exists)
        async def before_async(self, *args: Any, **kwargs: Any) -> None:
            return await super().before_async(*args, **kwargs)

        @AfterRaising(AsyncLog.exists)
        async def after_raising_async(self, error: Exception) -> None:
            return await super().after_raising_async(error)

        @AfterReturning(AsyncLog.exists)
        async def after_returning_async(self, result: Any) -> None:
            return await super().after_returning_async(result)

        @After(AsyncLog.exists)
        async def after_async(self) -> None:
            return await super().after_async()

        @Around(AsyncLog.exists)
        async def around_async(
            self, joinpoint: AsyncFunc, *args: Any, **kwargs: Any
        ) -> Any:
            return await super().around_async(joinpoint, *args, **kwargs)

    @Pod()
    class EchoService:
        @AsyncLog()
        async def echo(self, message: str) -> str:
            return message

    @Pod()
    class AnotherService:
        async def echo(self, message: str) -> str:
            return message

    context: ApplicationContext = ApplicationContext()

    context.add(EchoService)
    context.add(AnotherService)
    context.add(AsyncLogAdvisor)

    context.start()

    assert (
        await context.get(type_=EchoService).echo(message="Hello World!")
        == "Hello World!"
    )
    assert (
        await context.get(type_=AnotherService).echo(message="Hello World!")
        == "Hello World!"
    )
    assert len(logs) == 0

    assert dir(context.get(type_=EchoService)) == dir(EchoService())


@pytest.mark.asyncio
async def test_async_aop_with_no_implementations_raise_error() -> None:
    """AsyncAspect 구현체 없이 비동기 메서드에서 예외 발생 시 정상적으로 전파됨을 검증한다."""
    logs: list[str] = []

    @dataclass
    class AsyncLog(FunctionAnnotation):
        def __call__(
            self, obj: Callable[..., Awaitable[AnyT]]
        ) -> Callable[..., Awaitable[AnyT]]:
            return super().__call__(obj)

    @AsyncAspect()
    class AsyncLogAdvisor(IAsyncAspect): ...

    @Pod()
    class EchoService:
        @AsyncLog()
        async def echo(self, message: str) -> str:
            raise RuntimeError

    context: ApplicationContext = ApplicationContext()

    context.add(EchoService)
    context.add(AsyncLogAdvisor)

    context.start()

    service: EchoService = context.get(type_=EchoService)
    with pytest.raises(RuntimeError):
        assert await service.echo(message="Hello World!") == "Hello World!"
    assert len(logs) == 0


@pytest.mark.asyncio
async def test_async_aop_with_implementations_raise_error() -> None:
    """비동기 메서드에서 예외 발생 시 AfterRaising advice가 호출됨을 검증한다."""
    logs: list[str] = []

    @dataclass
    class AsyncLog(FunctionAnnotation):
        def __call__(
            self, obj: Callable[..., Awaitable[AnyT]]
        ) -> Callable[..., Awaitable[AnyT]]:
            return super().__call__(obj)

    @AsyncAspect()
    class AsyncLogAdvisor(IAsyncAspect):
        @AfterRaising(AsyncLog.exists)
        async def after_raising_async(self, error: Exception) -> None:
            nonlocal logs
            logs.append(f"after_raising {type(error).__name__}")
            return await super().after_raising_async(error)

    @Pod()
    class EchoService:
        @AsyncLog()
        async def echo(self, message: str) -> str:
            raise RuntimeError

    context: ApplicationContext = ApplicationContext()

    context.add(EchoService)
    context.add(AsyncLogAdvisor)

    context.start()

    service: EchoService = context.get(type_=EchoService)
    with pytest.raises(RuntimeError):
        assert await service.echo(message="Hello World!") == "Hello World!"
    assert logs[0] == "after_raising RuntimeError"


@pytest.mark.asyncio
async def test_async_aop_raise_error() -> None:
    """비동기 메서드 예외 발생 시 모든 advice가 올바른 순서로 동작함을 검증한다."""
    logs: list[str] = []

    @dataclass
    class AsyncLog(FunctionAnnotation):
        def __call__(
            self, obj: Callable[..., Awaitable[AnyT]]
        ) -> Callable[..., Awaitable[AnyT]]:
            return super().__call__(obj)

    @AsyncAspect()
    class AsyncLogAdvisor(IAsyncAspect):
        @Before(AsyncLog.exists)
        async def before_async(self, *args: Any, **kwargs: Any) -> None:
            nonlocal logs
            logs.append(f"before {args}, {kwargs}")

        @AfterRaising(AsyncLog.exists)
        async def after_raising_async(self, error: Exception) -> None:
            nonlocal logs
            logs.append(f"after_raising {error}")

        @AfterReturning(AsyncLog.exists)
        async def after_returning_async(self, result: Any) -> None:
            nonlocal logs
            logs.append(f"after_returning {result}")

        @After(AsyncLog.exists)
        async def after_async(self) -> None:
            nonlocal logs
            logs.append("after")

        @Around(AsyncLog.exists)
        async def around_async(
            self,
            joinpoint: AsyncFunc,
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            nonlocal logs
            try:
                result = await joinpoint(*args, **kwargs)
            except Exception as e:
                logs.append(f"around {args}, {kwargs} {e}")
                raise
            else:
                logs.append(f"around {args}, {kwargs} {result}")
                return result

    @Pod()
    class EchoService:
        @AsyncLog()
        async def echo(self, message: str) -> str:
            raise RuntimeError

    context: ApplicationContext = ApplicationContext()

    context.add(EchoService)
    context.add(AsyncLogAdvisor)

    context.start()

    service: EchoService = context.get(type_=EchoService)
    with pytest.raises(RuntimeError):
        assert await service.echo(message="Hello World!") == "Hello World!"
    assert logs[0] == "before (), {'message': 'Hello World!'}"
    assert logs[1] == "around (), {'message': 'Hello World!'} "
    assert logs[2] == "after_raising "
    assert logs[3] == "after"


@pytest.mark.asyncio
async def test_async_aop_that_does_not_have_any_aspects() -> None:
    """AsyncAspect가 정의되지 않은 상태에서도 비동기 메서드가 정상 동작함을 검증한다."""
    logs: list[str] = []

    @dataclass
    class AsyncLog(FunctionAnnotation):
        def __call__(
            self, obj: Callable[..., Awaitable[AnyT]]
        ) -> Callable[..., Awaitable[AnyT]]:
            return super().__call__(obj)

    @AsyncAspect()
    class AsyncLogAdvisor(IAsyncAspect):
        async def before_async(self, *args: Any, **kwargs: Any) -> None:
            return await super().before_async(*args, **kwargs)

        async def after_returning_async(self, result: Any) -> None:
            return await super().after_returning_async(result)

        async def after_raising_async(self, error: Exception) -> None:
            return await super().after_raising_async(error)

        async def after_async(self) -> None:
            return await super().after_async()

        async def around_async(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:
            return await super().around_async(joinpoint, *args, **kwargs)

    @Pod()
    class AsyncEchoService:
        @AsyncLog()
        async def echo(self, message: str) -> str:
            return message

    context: ApplicationContext = ApplicationContext()

    context.add(AsyncEchoService)
    context.add(AsyncLogAdvisor)

    context.start()

    service: AsyncEchoService = context.get(type_=AsyncEchoService)
    assert await service.echo(message="Hello World!") == "Hello World!"
    assert len(logs) == 0


@pytest.mark.asyncio
async def test_async_aop_with_no_method() -> None:
    """@AsyncLog 어노테이션이 적용된 메서드가 없는 Pod에서 속성 접근이 정상 동작함을 검증한다."""
    logs: list[str] = []

    @dataclass
    class AsyncLog(FunctionAnnotation):
        def __call__(
            self, obj: Callable[..., Awaitable[AnyT]]
        ) -> Callable[..., Awaitable[AnyT]]:
            return super().__call__(obj)

    @AsyncAspect()
    class AsyncLogAdvisor(IAsyncAspect):
        @Before(AsyncLog.exists)
        async def before_async(self, *args: Any, **kwargs: Any) -> None:
            nonlocal logs
            logs.append(f"before {args}, {kwargs}")

        @AfterRaising(AsyncLog.exists)
        async def after_raising_async(self, error: Exception) -> None:
            nonlocal logs
            logs.append(f"after_raising {error}")

        @AfterReturning(AsyncLog.exists)
        async def after_returning_async(self, result: Any) -> None:
            nonlocal logs
            logs.append(f"after_returning {result}")

        @After(AsyncLog.exists)
        async def after_async(self) -> None:
            nonlocal logs
            logs.append("after")

        @Around(AsyncLog.exists)
        async def around_async(
            self,
            joinpoint: AsyncFunc,
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            nonlocal logs
            try:
                result = await joinpoint(*args, **kwargs)
            except Exception as e:
                logs.append(f"around {args}, {kwargs} {e}")
                raise
            else:
                logs.append(f"around {args}, {kwargs} {result}")
                return result

    @Pod()
    class AsyncEchoService:
        message = "Hello World!"

    context: ApplicationContext = ApplicationContext()

    context.add(AsyncEchoService)
    context.add(AsyncLogAdvisor)

    context.start()

    service: AsyncEchoService = context.get(type_=AsyncEchoService)
    assert service.message == "Hello World!"
    assert len(logs) == 0


def test_aspect_skips_property_getters_during_introspection() -> None:
    """AOP 인트로스펙션 시 프로퍼티 게터가 호출되지 않음을 검증한다.

    Pod 멤버를 스캔하여 Aspect 매칭을 활때 프로퍼티 게터가 실행되면
    초기화되지 않은 상태에서 에러가 발생할 수 있는 부작용을 방지한다.
    """

    class PropertyAccessedError(Exception):
        """Raised when property getter is unexpectedly invoked."""

    @dataclass
    class Log(FunctionAnnotation): ...

    @Aspect()
    class LogAdvisor(IAspect):
        @Before(Log.exists)
        def before(self, *args: Any, **kwargs: Any) -> None:
            pass

    @Pod()
    class ServiceWithProperty:
        initialized: bool = False

        @property
        def dangerous_property(self) -> str:
            if not self.initialized:
                raise PropertyAccessedError("Property accessed before initialization!")
            return "value"

        @Log()
        def do_work(self) -> str:
            return "done"

    context: ApplicationContext = ApplicationContext()
    context.add(ServiceWithProperty)
    context.add(LogAdvisor)

    # This should NOT raise PropertyAccessedError
    context.start()

    service: ServiceWithProperty = context.get(type_=ServiceWithProperty)
    service.initialized = True
    assert service.do_work() == "done"
    assert service.dangerous_property == "value"


def test_aspect_matches_callable_class_expect_fallthrough_branches() -> None:
    """Aspect.matches()에 callable 클래스를 전달할 때 모든 pointcut 분기를 검증한다."""

    @dataclass
    class Log(FunctionAnnotation): ...

    @Aspect()
    class LogAdvisor(IAspect):
        @Around(Log.exists)
        def around(
            self,
            joinpoint: Func,
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            return joinpoint(*args, **kwargs)

    @Pod()
    class Matched:
        @Log()
        def method(self) -> str:
            return "ok"

    @Pod()
    class Unmatched:
        def method(self) -> str:
            return "ok"

    aspect_meta = Aspect.get(LogAdvisor)

    # callable(Matched) → True, Around advice matches → True (via get_callable_methods)
    assert aspect_meta.matches(Matched) is True
    # callable(Unmatched) → True, Around advice.matches(Unmatched) → False,
    # for loop exhausted → falls through to get_callable_methods → still no match
    assert aspect_meta.matches(Unmatched) is False


@pytest.mark.asyncio
async def test_async_aspect_matches_callable_class_expect_fallthrough_branches() -> (
    None
):
    """AsyncAspect.matches()에 callable 클래스를 전달할 때 모든 pointcut 분기를 검증한다."""

    @dataclass
    class AsyncLog(FunctionAnnotation): ...

    @AsyncAspect()
    class AsyncLogAdvisor(IAsyncAspect):
        @Around(AsyncLog.exists)
        async def around_async(
            self,
            joinpoint: Callable[..., Awaitable[AnyT]],
            *args: Any,
            **kwargs: Any,
        ) -> AnyT:
            return await joinpoint(*args, **kwargs)

    @Pod()
    class Matched:
        @AsyncLog()
        async def method(self) -> str:
            return "ok"

    @Pod()
    class Unmatched:
        async def method(self) -> str:
            return "ok"

    aspect_meta = AsyncAspect.get(AsyncLogAdvisor)

    assert aspect_meta.matches(Matched) is True
    assert aspect_meta.matches(Unmatched) is False
