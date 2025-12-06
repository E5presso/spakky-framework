import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod


def test_singleton_thread_safety_expect_single_instance() -> None:
    """
    Test that Singleton Pods are instantiated only once even when accessed concurrently
    by multiple threads. This verifies the thread-safety of the lazy initialization logic.
    """

    init_count = 0

    @Pod(scope=Pod.Scope.SINGLETON)
    class SlowInitPod:
        id: UUID

        def __init__(self) -> None:
            nonlocal init_count
            # Simulate slow initialization to increase chance of race condition
            time.sleep(0.1)
            self.id = uuid4()
            init_count += 1

    context = ApplicationContext()
    context.add(SlowInitPod)

    num_threads = 10
    results: list[SlowInitPod] = []

    def get_pod() -> SlowInitPod:
        return context.get(SlowInitPod)

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(get_pod) for _ in range(num_threads)]
        results = [f.result() for f in futures]

    # Verify all instances are identical
    first_instance = results[0]
    for instance in results[1:]:
        assert instance is first_instance, (
            "Singleton instance should be the same across all threads"
        )
        assert instance.id == first_instance.id

    # Verify constructor was called exactly once
    assert init_count == 1, (
        f"Constructor should be called exactly once, but was called {init_count} times"
    )


def test_singleton_deadlock_prevention() -> None:
    """
    Test specifically for the deadlock scenario where a lock might be re-acquired incorrectly.
    This ensures the fix for the reentrant lock issue works.
    """

    @Pod(scope=Pod.Scope.SINGLETON)
    class RecursivePod:
        def __init__(self) -> None:
            pass

    context = ApplicationContext()
    context.add(RecursivePod)

    # If there was a deadlock (e.g. re-acquiring a non-reentrant lock),
    # this would hang indefinitely. We use a timeout to fail if it hangs.

    def access_pod() -> None:
        context.get(RecursivePod)

    # Create a thread to access the pod
    t = threading.Thread(target=access_pod)
    t.start()
    t.join(timeout=2.0)  # Wait max 2 seconds

    assert not t.is_alive(), "Thread failed to complete, likely deadlocked"
