import gc
import sys
from typing import Any

import pytest

from spakky.aop.aspect import Aspect, AsyncAspect
from spakky.aop.interfaces.aspect import IAspect, IAsyncAspect
from spakky.aop.pointcut import Around
from spakky.application.application import SpakkyApplication
from spakky.application.application_context import ApplicationContext
from spakky.core.types import AsyncFunc, Func
from spakky.pod.annotations.pod import Pod
from spakky.pod.interfaces.container import IContainer
from spakky.stereotype.usecase import UseCase


@Aspect()
class MemoryTestAspect(IAspect):
    call_count: int = 0

    @Around(lambda x: hasattr(x, "__name__") and "execute" in x.__name__)
    def around(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:
        MemoryTestAspect.call_count += 1
        return joinpoint(*args, **kwargs)


@AsyncAspect()
class AsyncMemoryTestAspect(IAsyncAspect):
    call_count: int = 0

    @Around(lambda x: hasattr(x, "__name__") and "execute" in x.__name__)
    async def around_async(
        self, joinpoint: AsyncFunc, *args: Any, **kwargs: Any
    ) -> Any:
        AsyncMemoryTestAspect.call_count += 1
        return await joinpoint(*args, **kwargs)


@UseCase(scope=Pod.Scope.SINGLETON)
class SingletonService:
    def execute(self) -> str:
        return "singleton"


@UseCase(scope=Pod.Scope.PROTOTYPE)
class PrototypeService:
    instance_id: int

    def __init__(self) -> None:
        self.instance_id = id(self)

    def execute(self) -> str:
        return f"prototype-{self.instance_id}"


@UseCase(scope=Pod.Scope.PROTOTYPE)
class AsyncPrototypeService:
    instance_id: int

    def __init__(self) -> None:
        self.instance_id = id(self)

    async def execute(self) -> str:
        return f"async-prototype-{self.instance_id}"


@pytest.fixture
def memory_test_app() -> SpakkyApplication:
    app = (
        SpakkyApplication(ApplicationContext())
        .add(MemoryTestAspect)
        .add(AsyncMemoryTestAspect)
        .add(SingletonService)
        .add(PrototypeService)
        .add(AsyncPrototypeService)
        .start()
    )
    return app


def test_singleton_cache_persists(memory_test_app: SpakkyApplication) -> None:
    container: IContainer = memory_test_app.container

    # Get singleton instance
    service: SingletonService = container.get(SingletonService)
    method_id_1 = id(service.execute)

    # Call multiple times
    for _ in range(5):
        assert service.execute() == "singleton"

    # Method ID should remain the same (cache hit)
    method_id_2 = id(service.execute)
    assert method_id_1 == method_id_2


def test_prototype_instances_are_independent(
    memory_test_app: SpakkyApplication,
) -> None:
    container: IContainer = memory_test_app.container

    # Create multiple prototype instances
    service1: PrototypeService = container.get(PrototypeService)
    service2: PrototypeService = container.get(PrototypeService)
    service3: PrototypeService = container.get(PrototypeService)

    # Each instance should be different
    assert service1.instance_id != service2.instance_id
    assert service2.instance_id != service3.instance_id
    assert service1.instance_id != service3.instance_id

    # Results should be different (different instance_id embedded)
    result1 = service1.execute()
    result2 = service2.execute()
    result3 = service3.execute()

    assert result1 != result2
    assert result2 != result3
    assert result1 != result3


def test_prototype_cache_releases_after_gc(
    memory_test_app: SpakkyApplication,
) -> None:
    container: IContainer = memory_test_app.container

    # Get the AspectProxyHandler from a prototype instance
    initial_service: PrototypeService = container.get(PrototypeService)
    initial_result = initial_service.execute()
    assert initial_result.startswith("prototype-")

    # Track method references before creating more instances
    initial_refcount = sys.getrefcount(initial_service.execute)

    # Create many prototype instances and let them go out of scope
    method_ids: list[int] = []
    for i in range(10):
        service = container.get(PrototypeService)
        method_ids.append(id(service.execute))
        _ = service.execute()  # Trigger aspect and cache population
        # service goes out of scope here

    # Force garbage collection
    gc.collect()

    # Create a new instance and verify it works
    final_service: PrototypeService = container.get(PrototypeService)
    final_result = final_service.execute()
    assert final_result.startswith("prototype-")

    # The refcount should not have grown significantly
    # (Some growth is acceptable due to Python's object model)
    final_refcount = sys.getrefcount(final_service.execute)

    # If WeakKeyDictionary is working, refcount should be similar
    # Allow some tolerance for Python's internal references
    refcount_growth = final_refcount - initial_refcount
    assert refcount_growth < 5, (
        f"Reference count grew by {refcount_growth}, possible memory leak"
    )


@pytest.mark.asyncio
async def test_async_prototype_cache_releases_after_gc(
    memory_test_app: SpakkyApplication,
) -> None:
    container: IContainer = memory_test_app.container

    # Get initial instance
    initial_service: AsyncPrototypeService = container.get(AsyncPrototypeService)
    initial_result = await initial_service.execute()
    assert initial_result.startswith("async-prototype-")

    # Track method references
    initial_refcount = sys.getrefcount(initial_service.execute)

    # Create many async prototype instances
    for i in range(10):
        service = container.get(AsyncPrototypeService)
        _ = await service.execute()  # Trigger aspect and cache population
        # service goes out of scope here

    # Force garbage collection
    gc.collect()

    # Create a new instance and verify
    final_service: AsyncPrototypeService = container.get(AsyncPrototypeService)
    final_result = await final_service.execute()
    assert final_result.startswith("async-prototype-")

    # Check refcount growth
    final_refcount = sys.getrefcount(final_service.execute)
    refcount_growth = final_refcount - initial_refcount

    assert refcount_growth < 5, (
        f"Reference count grew by {refcount_growth}, possible memory leak"
    )


def test_aspect_applies_to_all_prototype_instances(
    memory_test_app: SpakkyApplication,
) -> None:
    container: IContainer = memory_test_app.container

    # Reset counter
    MemoryTestAspect.call_count = 0

    # Create multiple prototype instances and call their methods
    instances = [container.get(PrototypeService) for _ in range(5)]

    for instance in instances:
        result = instance.execute()
        assert result.startswith("prototype-")

    # Aspect should have been called for each instance
    assert MemoryTestAspect.call_count == 5


@pytest.mark.asyncio
async def test_async_aspect_applies_to_all_prototype_instances(
    memory_test_app: SpakkyApplication,
) -> None:
    container: IContainer = memory_test_app.container

    # Reset counter
    AsyncMemoryTestAspect.call_count = 0

    # Create multiple async prototype instances
    instances = [container.get(AsyncPrototypeService) for _ in range(5)]

    for instance in instances:
        result = await instance.execute()
        assert result.startswith("async-prototype-")

    # Aspect should have been called for each instance
    assert AsyncMemoryTestAspect.call_count == 5


def test_cache_behavior_with_explicit_deletion(
    memory_test_app: SpakkyApplication,
) -> None:
    container: IContainer = memory_test_app.container

    # Create instances
    service1 = container.get(PrototypeService)
    service2 = container.get(PrototypeService)

    # Execute to populate cache
    result1 = service1.execute()
    result2 = service2.execute()

    # Results should be different (different instances)
    assert result1 != result2
    assert result1.startswith("prototype-")
    assert result2.startswith("prototype-")

    # Explicitly delete first instance
    del service1
    gc.collect()

    # Second instance should still work
    result2_again = service2.execute()
    assert result2_again == result2

    # Create a new instance - should work fine
    service3 = container.get(PrototypeService)
    result3 = service3.execute()
    assert result3.startswith("prototype-")
    assert result3 != result2


def test_memory_stability_under_load(memory_test_app: SpakkyApplication) -> None:
    container: IContainer = memory_test_app.container

    # Baseline memory check
    baseline_service: PrototypeService = container.get(PrototypeService)
    baseline_refcount = sys.getrefcount(baseline_service.execute)
    del baseline_service
    gc.collect()

    # High load test - create 100 instances
    for i in range(100):
        service = container.get(PrototypeService)
        _ = service.execute()
        # Instance goes out of scope

    # Force cleanup
    gc.collect()

    # Check final state
    final_service = container.get(PrototypeService)
    final_refcount = sys.getrefcount(final_service.execute)

    # Memory should be stable
    refcount_growth = abs(final_refcount - baseline_refcount)
    assert refcount_growth < 10, (
        f"Memory unstable: refcount grew by {refcount_growth} after 100 iterations"
    )
