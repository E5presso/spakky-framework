"""Tests for event mediator implementations."""

import pytest
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractDomainEvent

from spakky.event.mediator.domain_event_mediator import (
    AsyncEventMediator,
    EventMediator,
)


@immutable
class UserCreatedEvent(AbstractDomainEvent):
    """Test event for user creation."""

    user_id: str
    username: str


@immutable
class OrderPlacedEvent(AbstractDomainEvent):
    """Test event for order placement."""

    order_id: str
    amount: float


def test_sync_mediator_register_and_dispatch_single_handler() -> None:
    """단일 핸들러가 dispatch된 이벤트를 수신함을 검증한다."""
    received_events: list[UserCreatedEvent] = []

    def handler(event: UserCreatedEvent) -> None:
        received_events.append(event)

    mediator = EventMediator()
    mediator.register(UserCreatedEvent, handler)

    event = UserCreatedEvent(user_id="123", username="alice")
    mediator.dispatch(event)

    assert len(received_events) == 1
    assert received_events[0].user_id == "123"
    assert received_events[0].username == "alice"


def test_sync_mediator_register_multiple_handlers_for_same_event() -> None:
    """여러 핸들러가 동일한 이벤트를 모두 수신함을 검증한다."""
    handler1_events: list[UserCreatedEvent] = []
    handler2_events: list[UserCreatedEvent] = []

    def handler1(event: UserCreatedEvent) -> None:
        handler1_events.append(event)

    def handler2(event: UserCreatedEvent) -> None:
        handler2_events.append(event)

    mediator = EventMediator()
    mediator.register(UserCreatedEvent, handler1)
    mediator.register(UserCreatedEvent, handler2)

    event = UserCreatedEvent(user_id="456", username="bob")
    mediator.dispatch(event)

    assert len(handler1_events) == 1
    assert len(handler2_events) == 1
    assert handler1_events[0] is event
    assert handler2_events[0] is event


def test_sync_mediator_dispatch_to_correct_event_type_only() -> None:
    """이벤트가 일치하는 타입의 핸들러에게만 dispatch됨을 검증한다."""
    user_events: list[UserCreatedEvent] = []
    order_events: list[OrderPlacedEvent] = []

    def user_handler(event: UserCreatedEvent) -> None:
        user_events.append(event)

    def order_handler(event: OrderPlacedEvent) -> None:
        order_events.append(event)

    mediator = EventMediator()
    mediator.register(UserCreatedEvent, user_handler)
    mediator.register(OrderPlacedEvent, order_handler)

    user_event = UserCreatedEvent(user_id="789", username="charlie")
    mediator.dispatch(user_event)

    assert len(user_events) == 1
    assert len(order_events) == 0


def test_sync_mediator_dispatch_without_handlers_does_not_error() -> None:
    """등록된 핸들러가 없을 때 dispatch해도 예외가 발생하지 않음을 검증한다."""
    mediator = EventMediator()

    event = UserCreatedEvent(user_id="999", username="dave")
    # Should not raise
    mediator.dispatch(event)


def test_sync_mediator_handler_error_does_not_stop_other_handlers() -> None:
    """하나의 핸들러가 예외를 발생시켜도 다른 핸들러들이 계속 실행됨을 검증한다."""
    handler1_called = False
    handler2_called = False

    def failing_handler(event: UserCreatedEvent) -> None:
        nonlocal handler1_called
        handler1_called = True
        raise ValueError("Handler failed")

    def success_handler(event: UserCreatedEvent) -> None:
        nonlocal handler2_called
        handler2_called = True

    mediator = EventMediator()
    mediator.register(UserCreatedEvent, failing_handler)
    mediator.register(UserCreatedEvent, success_handler)

    event = UserCreatedEvent(user_id="000", username="eve")
    # Should not raise, should continue to other handlers
    mediator.dispatch(event)

    assert handler1_called
    assert handler2_called


@pytest.mark.asyncio
async def test_async_mediator_register_and_dispatch_single_handler() -> None:
    """async 핸들러가 dispatch된 이벤트를 수신함을 검증한다."""
    received_events: list[UserCreatedEvent] = []

    async def handler(event: UserCreatedEvent) -> None:
        received_events.append(event)

    mediator = AsyncEventMediator()
    mediator.register(UserCreatedEvent, handler)

    event = UserCreatedEvent(user_id="async-123", username="async-alice")
    await mediator.dispatch(event)

    assert len(received_events) == 1
    assert received_events[0].user_id == "async-123"


@pytest.mark.asyncio
async def test_async_mediator_register_multiple_handlers_for_same_event() -> None:
    """여러 async 핸들러가 동일한 이벤트를 모두 수신함을 검증한다."""
    handler1_events: list[UserCreatedEvent] = []
    handler2_events: list[UserCreatedEvent] = []

    async def handler1(event: UserCreatedEvent) -> None:
        handler1_events.append(event)

    async def handler2(event: UserCreatedEvent) -> None:
        handler2_events.append(event)

    mediator = AsyncEventMediator()
    mediator.register(UserCreatedEvent, handler1)
    mediator.register(UserCreatedEvent, handler2)

    event = UserCreatedEvent(user_id="async-456", username="async-bob")
    await mediator.dispatch(event)

    assert len(handler1_events) == 1
    assert len(handler2_events) == 1


@pytest.mark.asyncio
async def test_async_mediator_dispatch_to_correct_event_type_only() -> None:
    """async 이벤트가 일치하는 타입의 핸들러에게만 dispatch됨을 검증한다."""
    user_events: list[UserCreatedEvent] = []
    order_events: list[OrderPlacedEvent] = []

    async def user_handler(event: UserCreatedEvent) -> None:
        user_events.append(event)

    async def order_handler(event: OrderPlacedEvent) -> None:
        order_events.append(event)

    mediator = AsyncEventMediator()
    mediator.register(UserCreatedEvent, user_handler)
    mediator.register(OrderPlacedEvent, order_handler)

    user_event = UserCreatedEvent(user_id="async-789", username="async-charlie")
    await mediator.dispatch(user_event)

    assert len(user_events) == 1
    assert len(order_events) == 0


@pytest.mark.asyncio
async def test_async_mediator_dispatch_without_handlers_does_not_error() -> None:
    """등록된 핸들러가 없을 때 async dispatch해도 예외가 발생하지 않음을 검증한다."""
    mediator = AsyncEventMediator()

    event = UserCreatedEvent(user_id="async-999", username="async-dave")
    # Should not raise
    await mediator.dispatch(event)


@pytest.mark.asyncio
async def test_async_mediator_handler_error_does_not_stop_other_handlers() -> None:
    """하나의 async 핸들러가 예외를 발생시켜도 다른 핸들러들이 계속 실행됨을 검증한다."""
    handler1_called = False
    handler2_called = False

    async def failing_handler(event: UserCreatedEvent) -> None:
        nonlocal handler1_called
        handler1_called = True
        raise ValueError("Async handler failed")

    async def success_handler(event: UserCreatedEvent) -> None:
        nonlocal handler2_called
        handler2_called = True

    mediator = AsyncEventMediator()
    mediator.register(UserCreatedEvent, failing_handler)
    mediator.register(UserCreatedEvent, success_handler)

    event = UserCreatedEvent(user_id="async-000", username="async-eve")
    # Should not raise, should continue to other handlers
    await mediator.dispatch(event)

    assert handler1_called
    assert handler2_called
