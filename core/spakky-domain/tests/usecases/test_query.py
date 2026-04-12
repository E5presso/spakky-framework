import asyncio
from dataclasses import dataclass
from typing import Awaitable

from typing_extensions import override

from spakky.domain.application.query import (
    AbstractQuery,
    IAsyncQueryUseCase,
    IQueryUseCase,
)


def test_abstract_query() -> None:
    """AbstractQuery의 인스턴스를 생성할 수 있음을 검증한다."""

    class _TestQuery(AbstractQuery):
        pass

    query = _TestQuery()
    assert isinstance(query, AbstractQuery)


def test_sync_query_usecase_expect_runs_and_returns_result() -> None:
    """동기 IQueryUseCase 구현이 쿼리를 실행하고 결과를 반환함을 검증한다."""

    @dataclass(frozen=True)
    class _LookupQuery(AbstractQuery):
        key: str

    class _LookupQueryUseCase(IQueryUseCase[_LookupQuery, str]):
        @override
        def run(self, query: _LookupQuery) -> str:
            return f"value:{query.key}"

    use_case = _LookupQueryUseCase()
    result = use_case.run(_LookupQuery(key="k"))

    assert result == "value:k"


def test_async_query_usecase_with_async_def_expect_awaitable_result() -> None:
    """비동기 IAsyncQueryUseCase를 async def로 구현해도 유효함을 검증한다.

    Coroutine은 Awaitable의 subtype이므로 추상 선언이
    ``def run(...) -> Awaitable[ResultT_co]`` 이어도 ``async def run`` 구현이
    정상적으로 호환됨을 검증한다.
    """

    @dataclass(frozen=True)
    class _CountQuery(AbstractQuery):
        value: str

    class _CountQueryUseCase(IAsyncQueryUseCase[_CountQuery, int]):
        @override
        async def run(self, query: _CountQuery) -> int:
            return len(query.value)

    use_case = _CountQueryUseCase()
    awaitable = use_case.run(_CountQuery(value="hello"))

    assert isinstance(awaitable, Awaitable)

    async def _drive() -> int:
        return await awaitable

    result = asyncio.run(_drive())
    assert result == 5


def test_async_query_usecase_with_awaitable_return_expect_awaitable_result() -> None:
    """비동기 IAsyncQueryUseCase를 동기 메서드가 Awaitable을 반환하는 방식으로
    구현해도 유효함을 검증한다."""

    @dataclass(frozen=True)
    class _UpperQuery(AbstractQuery):
        value: str

    class _UpperQueryUseCase(IAsyncQueryUseCase[_UpperQuery, str]):
        @override
        def run(self, query: _UpperQuery) -> Awaitable[str]:
            async def _execute() -> str:
                return query.value.upper()

            return _execute()

    use_case = _UpperQueryUseCase()

    async def _drive() -> str:
        return await use_case.run(_UpperQuery(value="hi"))

    result = asyncio.run(_drive())

    assert result == "HI"
