import asyncio

import pytest

from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod


def test_get_singleton_scoped_pod() -> None:
    """SINGLETON 스코프 Pod이 동일한 인스턴스를 반환함을 검증한다."""

    @Pod(scope=Pod.Scope.SINGLETON)
    class A: ...

    context = ApplicationContext()
    context.add(A)

    context.start()

    a1 = context.get(A)
    a2 = context.get(A)

    assert a1 is a2


def test_get_prototype_scoped_pod() -> None:
    """PROTOTYPE 스코프 Pod이 매번 새로운 인스턴스를 반환함을 검증한다."""

    @Pod(scope=Pod.Scope.PROTOTYPE)
    class A: ...

    context = ApplicationContext()
    context.add(A)

    context.start()

    a1 = context.get(A)
    a2 = context.get(A)

    assert a1 is not a2


@pytest.mark.asyncio
async def test_context_scoped_pod_creates_isolated_instances_per_async_flow() -> None:
    """CONTEXT 스코프 Pod이 비동기 흐름별로 독립된 인스턴스를 생성함을 검증한다."""

    @Pod(scope=Pod.Scope.CONTEXT)
    class A: ...

    context = ApplicationContext()
    context.add(A)
    context.start()

    results: list[A] = []

    async def task_logic() -> None:
        context.clear_context()
        instance1 = context.get(A)
        await asyncio.sleep(0.01)
        instance2 = context.get(A)
        assert instance1 is instance2
        results.append(instance1)

    await asyncio.gather(*(task_logic() for _ in range(5)))
    assert len(set(map(id, results))) == 5


def test_start_stop_restores_previous_default_event_loop() -> None:
    """start()/stop()가 기존 default event loop를 보존하고 복원함을 검증한다."""

    previous_event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(previous_event_loop)

    context = ApplicationContext()

    try:
        context.start()
        context.stop()

        assert asyncio.get_event_loop() is previous_event_loop
    finally:
        asyncio.set_event_loop(None)
        previous_event_loop.close()
