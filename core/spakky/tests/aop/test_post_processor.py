import pytest

from spakky.core.application.application_context import ApplicationContext
from tests.aop.apps.dummy import AsyncDummyUseCase, DummyUseCase


def test_post_processor_with_complete_application_context(
    application_context: ApplicationContext,
) -> None:
    """ApplicationContext에서 AOP PostProcessor가 적용된 Pod이 정상 동작함을 검증한다."""
    usecase: DummyUseCase = application_context.get(type_=DummyUseCase)

    assert usecase.execute() == "Hello, World!"
    assert usecase.name == application_context.get(type_=str)


@pytest.mark.asyncio
async def test_post_processor_with_complete_application_context_async(
    application_context: ApplicationContext,
) -> None:
    """ApplicationContext에서 AOP PostProcessor가 적용된 비동기 Pod이 정상 동작함을 검증한다."""
    usecase: AsyncDummyUseCase = application_context.get(type_=AsyncDummyUseCase)

    assert await usecase.execute() == "Hello, World!"
    assert usecase.name == application_context.get(type_=str)


@pytest.mark.asyncio
async def test_async_advisor_cache_hit_expect_same_result(
    application_context: ApplicationContext,
) -> None:
    """같은 비동기 메서드를 두 번 호출하면 advisor 캐시가 히트된다."""
    usecase: AsyncDummyUseCase = application_context.get(type_=AsyncDummyUseCase)

    # 첫 번째 호출 - 캐시 미스, advisor 생성
    first_result = await usecase.execute()
    # 두 번째 호출 - 캐시 히트 (line 69->79 커버)
    second_result = await usecase.execute()

    assert first_result == second_result == "Hello, World!"
