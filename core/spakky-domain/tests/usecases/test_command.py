import asyncio
from dataclasses import dataclass
from typing import Awaitable

from typing_extensions import override

from spakky.domain.application.command import (
    AbstractCommand,
    IAsyncCommandUseCase,
    ICommandUseCase,
)


def test_abstract_command() -> None:
    """AbstractCommand의 인스턴스를 생성할 수 있음을 검증한다."""

    class _TestCommand(AbstractCommand):
        pass

    command = _TestCommand()
    assert isinstance(command, AbstractCommand)


def test_sync_command_usecase_expect_runs_and_returns_result() -> None:
    """동기 ICommandUseCase 구현이 커맨드를 실행하고 결과를 반환함을 검증한다."""

    @dataclass(frozen=True)
    class _AddCommand(AbstractCommand):
        left: int
        right: int

    class _AddCommandUseCase(ICommandUseCase[_AddCommand, int]):
        @override
        def run(self, command: _AddCommand) -> int:
            return command.left + command.right

    use_case = _AddCommandUseCase()
    result = use_case.run(_AddCommand(left=2, right=3))

    assert result == 5


def test_async_command_usecase_with_async_def_expect_awaitable_result() -> None:
    """비동기 IAsyncCommandUseCase를 async def로 구현해도 유효함을 검증한다.

    Coroutine은 Awaitable의 subtype이므로 추상 선언이
    ``def run(...) -> Awaitable[ResultT_co]`` 이어도 ``async def run`` 구현이
    정상적으로 호환됨을 검증한다.
    """

    @dataclass(frozen=True)
    class _MultiplyCommand(AbstractCommand):
        left: int
        right: int

    class _MultiplyCommandUseCase(IAsyncCommandUseCase[_MultiplyCommand, int]):
        @override
        async def run(self, command: _MultiplyCommand) -> int:
            return command.left * command.right

    use_case = _MultiplyCommandUseCase()
    awaitable = use_case.run(_MultiplyCommand(left=4, right=5))

    assert isinstance(awaitable, Awaitable)

    async def _drive() -> int:
        return await awaitable

    result = asyncio.run(_drive())
    assert result == 20


def test_async_command_usecase_with_awaitable_return_expect_awaitable_result() -> None:
    """비동기 IAsyncCommandUseCase를 동기 메서드가 Awaitable을 반환하는 방식으로
    구현해도 유효함을 검증한다."""

    @dataclass(frozen=True)
    class _EchoCommand(AbstractCommand):
        payload: str

    class _EchoCommandUseCase(IAsyncCommandUseCase[_EchoCommand, str]):
        @override
        def run(self, command: _EchoCommand) -> Awaitable[str]:
            async def _execute() -> str:
                return command.payload

            return _execute()

    use_case = _EchoCommandUseCase()

    async def _drive() -> str:
        return await use_case.run(_EchoCommand(payload="ok"))

    result = asyncio.run(_drive())

    assert result == "ok"
