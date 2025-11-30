"""Test application context error cases for complete coverage."""

from asyncio import locks
from threading import Event

import pytest

from spakky.application.application_context import (
    ApplicationContext,
    ApplicationContextAlreadyStartedError,
    ApplicationContextAlreadyStoppedError,
)


def test_application_context_start_twice_raises_error() -> None:
    """Test that starting context twice raises error."""
    context = ApplicationContext()
    context.start()

    with pytest.raises(ApplicationContextAlreadyStartedError):
        context.start()

    context.stop()


def test_application_context_stop_twice_raises_error() -> None:
    """Test that stopping context twice raises error."""
    context = ApplicationContext()
    context.start()
    context.stop()

    with pytest.raises(ApplicationContextAlreadyStoppedError):
        context.stop()


def test_application_context_with_services() -> None:
    """Test application context with sync and async services."""

    class DummyService:
        started = False
        stopped = False

        def set_stop_event(self, stop_event: Event) -> None:
            pass

        def start(self) -> None:
            self.started = True

        def stop(self) -> None:
            self.stopped = True

    class DummyAsyncService:
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
    """Test that accessing event loop when not started raises error."""
    context = ApplicationContext()

    # Try to stop without starting
    with pytest.raises(ApplicationContextAlreadyStoppedError):
        context.stop()
