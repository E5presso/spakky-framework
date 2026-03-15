"""Tests for Advisor and AsyncAdvisor — __getattr__ delegation."""

from typing import Any

import pytest

from spakky.core.aop.advisor import Advisor, AsyncAdvisor
from spakky.core.aop.interfaces.aspect import IAspect, IAsyncAspect
from spakky.core.common.types import AsyncFunc, Func


def _noop(*_args: Any, **_kwargs: Any) -> None:
    return None


class _StubAspect(IAspect):
    def before(self, *args: Any, **kwargs: Any) -> None:
        pass

    def after_returning(self, result: Any) -> None:
        pass

    def after_raising(self, error: Exception) -> None:
        pass

    def after(self) -> None:
        pass

    def around(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:
        return joinpoint(*args, **kwargs)


class _StubAsyncAspect(IAsyncAspect):
    async def around_async(
        self, joinpoint: AsyncFunc, *args: Any, **kwargs: Any
    ) -> Any:
        return await joinpoint(*args, **kwargs)


def test_advisor_getattr_delegates_to_next_function() -> None:
    """Advisor.__getattr__가 next 함수의 속성을 위임함을 검증한다."""

    def sample() -> None:
        """sample docstring"""

    sample.custom_attr = "hello"  # type: ignore[attr-defined]

    advisor = Advisor(instance=_StubAspect(), next=sample)
    assert advisor.custom_attr == "hello"  # type: ignore[attr-defined]
    assert advisor.__qualname__ == sample.__qualname__


@pytest.mark.asyncio
async def test_async_advisor_getattr_delegates_to_next_function() -> None:
    """AsyncAdvisor.__getattr__가 next 함수의 속성을 위임함을 검증한다."""

    async def async_sample() -> None:
        """async sample docstring"""

    async_sample.custom_attr = "world"  # type: ignore[attr-defined]

    advisor = AsyncAdvisor(instance=_StubAsyncAspect(), next=async_sample)
    assert advisor.custom_attr == "world"  # type: ignore[attr-defined]
    assert advisor.__qualname__ == async_sample.__qualname__
