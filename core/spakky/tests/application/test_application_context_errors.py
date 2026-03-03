"""Test application context error cases for complete coverage."""

from asyncio import locks
from threading import Event

import pytest

from spakky.core.application.application_context import (
    ApplicationContext,
    ApplicationContextAlreadyStartedError,
    ApplicationContextAlreadyStoppedError,
)
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


def test_event_loop_error_when_not_started() -> None:
    """컷텍스트가 시작되지 않은 상태에서 stop 호출 시 에러가 발생함을 검증한다."""
    context = ApplicationContext()

    # Try to stop without starting
    with pytest.raises(ApplicationContextAlreadyStoppedError):
        context.stop()
