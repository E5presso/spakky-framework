import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod


def test_singleton_thread_safety_expect_single_instance() -> None:
    """
    싱글톤 Pod가 여러 스레드에서 동시에 접근해도 단 한 번만 인스턴스화됨을 검증한다.
    지연 초기화 로직의 스레드 안전성을 확인한다.
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
    락이 잘못 재획득될 수 있는 데드락 시나리오를 테스트한다.
    재진입 락 문제에 대한 수정이 정상 동작함을 검증한다.
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


def test_concurrent_stop_calls_expect_safe() -> None:
    """
    여러 스레드에서 동시에 stop()을 호출해도 경합 조건이 발생하지 않음을 검증한다.
    첫 번째 호출만 성공하고, 나머지는 에러를 발생시켜야 한다.
    """
    from spakky.core.application.application_context import (
        ApplicationContextAlreadyStoppedError,
    )

    context = ApplicationContext()
    context.start()

    results: list[Exception | None] = []

    def try_stop() -> None:
        try:
            time.sleep(0.01)  # Small delay to increase race condition chance
            context.stop()
            results.append(None)  # Success
        except ApplicationContextAlreadyStoppedError as e:
            results.append(e)  # Expected error
        except Exception as e:
            results.append(e)  # Unexpected error

    # Try to stop from 5 threads concurrently
    threads = [threading.Thread(target=try_stop) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=3.0)
        assert not t.is_alive(), "Thread did not complete"

    # Exactly one should succeed, others should get AlreadyStopped error
    successful_stops = sum(1 for r in results if r is None)
    already_stopped_errors = sum(
        1 for r in results if isinstance(r, ApplicationContextAlreadyStoppedError)
    )

    assert successful_stops == 1, (
        f"Expected exactly 1 successful stop, got {successful_stops}"
    )
    assert already_stopped_errors == 4, (
        f"Expected 4 AlreadyStopped errors, got {already_stopped_errors}"
    )
    assert len(results) == 5, "All threads should have completed"
