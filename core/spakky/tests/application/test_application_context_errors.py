"""Test application context error cases for complete coverage."""

from asyncio import locks
from threading import Event

import pytest

from spakky.core.application.application_context import (
    ApplicationContext,
    ApplicationContextAlreadyStartedError,
    ApplicationContextAlreadyStoppedError,
    PodNameAlreadyExistsError,
)
from spakky.core.pod.annotations.pod import Pod
from spakky.core.service.background import IAsyncService, IService


def test_application_context_start_twice_raises_error() -> None:
    """컷텍스트를 두 번 시작하면 에러가 발생함을 검증한다."""
    context = ApplicationContext()
    context.start()

    with pytest.raises(ApplicationContextAlreadyStartedError):
        context.start()

    context.stop()


def test_application_context_stop_twice_raises_error() -> None:
    """컷텍스트를 두 번 중지하면 에러가 발생함을 검증한다."""
    context = ApplicationContext()
    context.start()
    context.stop()

    with pytest.raises(ApplicationContextAlreadyStoppedError):
        context.stop()


def test_application_context_with_services() -> None:
    """동기 및 비동기 서비스와 함께 컷텍스트가 정상 동작함을 검증한다."""

    class DummyService(IService):
        started = False
        stopped = False

        def set_stop_event(self, stop_event: Event) -> None:
            pass

        def start(self) -> None:
            self.started = True

        def stop(self) -> None:
            self.stopped = True

    class DummyAsyncService(IAsyncService):
        started = False
        stopped = False

        def set_stop_event(self, stop_event: locks.Event) -> None:
            pass

        async def start_async(self) -> None:
            self.started = True

        async def stop_async(self) -> None:
            self.stopped = True

    context = ApplicationContext()

    sync_service = DummyService()
    async_service = DummyAsyncService()

    context.add_service(sync_service)
    context.add_service(async_service)

    context.start()

    assert sync_service.started
    assert async_service.started

    context.stop()

    assert sync_service.stopped
    assert async_service.stopped


def test_application_context_start_failure_stops_started_sync_services() -> None:
    """Services started before a startup failure are stopped during rollback."""

    events: list[str] = []

    class StartedService(IService):
        def set_stop_event(self, stop_event: Event) -> None:
            self.stop_event = stop_event

        def start(self) -> None:
            events.append("started.start")

        def stop(self) -> None:
            events.append("started.stop")

    class FailingService(IService):
        def set_stop_event(self, stop_event: Event) -> None:
            self.stop_event = stop_event

        def start(self) -> None:
            events.append("failing.start")
            raise RuntimeError("service failed")

        def stop(self) -> None:
            events.append("failing.stop")

    context = ApplicationContext()
    context.add_service(StartedService())
    context.add_service(FailingService())

    with pytest.raises(RuntimeError, match="service failed"):
        context.start()

    assert events == ["started.start", "failing.start", "started.stop"]
    assert not context.is_started


def test_application_context_start_failure_stops_started_async_services() -> None:
    """Async services started before a startup failure are stopped during rollback."""

    events: list[str] = []

    class StartedAsyncService(IAsyncService):
        def set_stop_event(self, stop_event: locks.Event) -> None:
            self.stop_event = stop_event

        async def start_async(self) -> None:
            events.append("started.start")

        async def stop_async(self) -> None:
            events.append("started.stop")

    class FailingAsyncService(IAsyncService):
        def set_stop_event(self, stop_event: locks.Event) -> None:
            self.stop_event = stop_event

        async def start_async(self) -> None:
            events.append("failing.start")
            raise RuntimeError("async service failed")

        async def stop_async(self) -> None:
            events.append("failing.stop")

    context = ApplicationContext()
    context.add_service(StartedAsyncService())
    context.add_service(FailingAsyncService())

    with pytest.raises(RuntimeError, match="async service failed"):
        context.start()

    assert events == ["started.start", "failing.start", "started.stop"]
    assert not context.is_started


def test_event_loop_error_when_not_started() -> None:
    """컷텍스트가 시작되지 않은 상태에서 stop 호출 시 에러가 발생함을 검증한다."""
    context = ApplicationContext()

    # Try to stop without starting
    with pytest.raises(ApplicationContextAlreadyStoppedError):
        context.stop()


def test_add_pod_with_duplicate_name_raises_error() -> None:
    """같은 이름의 다른 Pod을 등록하면 에러가 발생함을 검증한다."""

    @Pod(name="duplicate")
    class FirstPod:
        pass

    @Pod(name="duplicate")
    class SecondPod:
        pass

    context = ApplicationContext()
    context.add(FirstPod)

    with pytest.raises(PodNameAlreadyExistsError):
        context.add(SecondPod)
