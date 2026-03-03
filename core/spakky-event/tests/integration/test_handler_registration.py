"""Integration tests for EventHandlerRegistrationPostProcessor.

Tests that @EventHandler methods are automatically registered with the
appropriate domain event consumers when the application starts.
"""

from spakky.core.application.application import SpakkyApplication

from spakky.event import (
    AsyncDomainEventMediator,
    DomainEventMediator,
)
from tests.integration.apps.models.order import Order


def test_sync_handler_registered_on_app_start(
    app: SpakkyApplication,
    sync_mediator: DomainEventMediator,
) -> None:
    """SpakkyApplication.start() 시 sync @EventHandler의 @on_event 메서드가 자동 등록됨을 검증한다."""
    # Then - Check that handlers are registered in the sync mediator
    handlers = sync_mediator._handlers.get(Order.Created, [])
    assert len(handlers) >= 1

    # Verify handler names contain our test handler
    handler_names = [h.__qualname__ for h in handlers]
    assert any("SyncOrderEventHandler" in name for name in handler_names)


def test_async_handler_registered_on_app_start(
    app: SpakkyApplication,
    async_mediator: AsyncDomainEventMediator,
) -> None:
    """SpakkyApplication.start() 시 async @EventHandler의 @on_event 메서드가 자동 등록됨을 검증한다."""
    # Then - Check that handlers are registered in the async mediator
    handlers = async_mediator._handlers.get(Order.Created, [])
    assert (
        len(handlers) >= 3
    )  # AsyncOrderEventHandler, SecondAsyncOrderEventHandler, FailingOrderEventHandler

    handler_names = [h.__qualname__ for h in handlers]
    assert any("AsyncOrderEventHandler" in name for name in handler_names)
    assert any("SecondAsyncOrderEventHandler" in name for name in handler_names)


def test_multiple_event_types_registered_for_same_handler(
    app: SpakkyApplication,
    async_mediator: AsyncDomainEventMediator,
) -> None:
    """하나의 @EventHandler에서 여러 @on_event 메서드가 각각의 이벤트 타입에 등록됨을 검증한다."""
    # Then - AsyncOrderEventHandler handles multiple event types
    created_handlers = async_mediator._handlers.get(Order.Created, [])
    item_added_handlers = async_mediator._handlers.get(Order.ItemAdded, [])
    cancelled_handlers = async_mediator._handlers.get(Order.Cancelled, [])

    # Check each event type has appropriate handlers
    created_handler_names = [h.__qualname__ for h in created_handlers]
    item_added_handler_names = [h.__qualname__ for h in item_added_handlers]
    cancelled_handler_names = [h.__qualname__ for h in cancelled_handlers]

    assert any(
        "AsyncOrderEventHandler.on_order_created" in name
        for name in created_handler_names
    )
    assert any(
        "AsyncOrderEventHandler.on_order_item_added" in name
        for name in item_added_handler_names
    )
    assert any(
        "AsyncOrderEventHandler.on_order_cancelled" in name
        for name in cancelled_handler_names
    )


def test_sync_and_async_handlers_registered_separately(
    app: SpakkyApplication,
    sync_mediator: DomainEventMediator,
    async_mediator: AsyncDomainEventMediator,
) -> None:
    """Sync 핸들러는 sync mediator에, async 핸들러는 async mediator에 등록됨을 검증한다."""
    # Then - Sync mediator should have sync handlers only
    sync_handlers = sync_mediator._handlers.get(Order.Created, [])
    sync_handler_names = [h.__qualname__ for h in sync_handlers]

    # SyncOrderEventHandler should be in sync mediator
    assert any("SyncOrderEventHandler" in name for name in sync_handler_names)

    # AsyncOrderEventHandler should NOT be in sync mediator
    assert not any("AsyncOrderEventHandler" in name for name in sync_handler_names)

    # Then - Async mediator should have async handlers only
    async_handlers = async_mediator._handlers.get(Order.Created, [])
    async_handler_names = [h.__qualname__ for h in async_handlers]

    # AsyncOrderEventHandler should be in async mediator
    assert any("AsyncOrderEventHandler" in name for name in async_handler_names)

    # SyncOrderEventHandler should NOT be in async mediator
    assert not any("SyncOrderEventHandler" in name for name in async_handler_names)
