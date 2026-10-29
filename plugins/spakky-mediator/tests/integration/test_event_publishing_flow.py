"""Integration tests for the full event publishing flow.

Tests the complete flow:
TransactionalEventPublishingAspect → EventPublisher → EventMediator → @EventHandler

These tests verify that domain events raised by aggregates are automatically
published and delivered to registered handlers after successful transaction completion.
"""

import pytest
from spakky.core.application.application import SpakkyApplication
from spakky.data.persistency.aggregate_collector import AggregateCollector

from tests.integration.apps.handlers.event_recorder import EventRecorder
from tests.integration.apps.models.order import Order
from tests.integration.apps.usecases.create_order import (
    AsyncCreateOrderUseCase,
    AsyncCreateOrderWithErrorUseCase,
    AsyncCreateOrderWithMultipleEventsUseCase,
    SyncCreateOrderUseCase,
)

# === Basic Success Flow Tests ===


def test_sync_transactional_usecase_single_event_expect_handler_invoked(
    app: SpakkyApplication,
    event_recorder: EventRecorder,
    collector: AggregateCollector,
) -> None:
    """Sync @Transactional UseCase에서 발생한 이벤트가 핸들러로 전달됨을 검증한다."""
    # Given
    use_case: SyncCreateOrderUseCase = app.container.get(type_=SyncCreateOrderUseCase)

    # When
    order = use_case.execute(customer_name="Alice", total_amount=100.0)

    # Then
    assert order.customer_name == "Alice"
    assert event_recorder.count_by_event_type(Order.Created) == 1

    events = event_recorder.get_events_by_handler(
        "SyncOrderEventHandler.on_order_created"
    )
    assert len(events) == 1
    assert isinstance(events[0], Order.Created)
    assert events[0].customer_name == "Alice"


@pytest.mark.asyncio
async def test_async_transactional_usecase_single_event_expect_handler_invoked(
    app: SpakkyApplication,
    event_recorder: EventRecorder,
    collector: AggregateCollector,
) -> None:
    """Async @Transactional UseCase에서 발생한 이벤트가 핸들러로 전달됨을 검증한다."""
    # Given
    use_case: AsyncCreateOrderUseCase = app.container.get(type_=AsyncCreateOrderUseCase)

    # When
    order = await use_case.execute(customer_name="Bob", total_amount=200.0)

    # Then
    assert order.customer_name == "Bob"
    assert event_recorder.count_by_event_type(Order.Created) >= 1

    events = event_recorder.get_events_by_handler(
        "AsyncOrderEventHandler.on_order_created"
    )
    assert len(events) == 1
    assert isinstance(events[0], Order.Created)
    assert events[0].customer_name == "Bob"


@pytest.mark.asyncio
async def test_async_transactional_usecase_multiple_events_expect_all_handlers_invoked(
    app: SpakkyApplication,
    event_recorder: EventRecorder,
    collector: AggregateCollector,
) -> None:
    """하나의 aggregate에서 여러 이벤트 발생 시 모든 핸들러가 호출됨을 검증한다."""
    # Given
    use_case: AsyncCreateOrderWithMultipleEventsUseCase = app.container.get(
        type_=AsyncCreateOrderWithMultipleEventsUseCase
    )
    items = [("Widget", 2), ("Gadget", 1)]

    # When
    order = await use_case.execute(
        customer_name="Charlie",
        total_amount=300.0,
        items=items,
    )

    # Then
    assert order.customer_name == "Charlie"
    assert len(order.items) == 2

    # Order.Created + 2 Order.ItemAdded = 3 events total
    assert event_recorder.count_by_event_type(Order.Created) >= 1
    assert event_recorder.count_by_event_type(Order.ItemAdded) == 2

    item_events = event_recorder.get_events_by_handler(
        "AsyncOrderEventHandler.on_order_item_added"
    )
    assert len(item_events) == 2
    item_names = [e.item_name for e in item_events if isinstance(e, Order.ItemAdded)]
    assert "Widget" in item_names
    assert "Gadget" in item_names


# === Failure Scenario Tests ===


@pytest.mark.asyncio
async def test_async_transactional_usecase_exception_expect_no_events_published(
    app: SpakkyApplication,
    event_recorder: EventRecorder,
    collector: AggregateCollector,
) -> None:
    """UseCase에서 예외 발생 시 이벤트가 발행되지 않음을 검증한다."""
    # Given
    use_case: AsyncCreateOrderWithErrorUseCase = app.container.get(
        type_=AsyncCreateOrderWithErrorUseCase
    )

    # When
    with pytest.raises(RuntimeError, match="Transaction failed intentionally"):
        await use_case.execute(customer_name="FailUser", total_amount=500.0)

    # Then - No events should be published
    assert event_recorder.count_by_event_type(Order.Created) == 0
    assert len(event_recorder.records) == 0


# === Multiple Handlers Tests ===


@pytest.mark.asyncio
async def test_multiple_handlers_for_same_event_expect_all_invoked(
    app: SpakkyApplication,
    event_recorder: EventRecorder,
    collector: AggregateCollector,
) -> None:
    """같은 이벤트 타입에 여러 핸들러 등록 시 모두 호출됨을 검증한다."""
    # Given
    use_case: AsyncCreateOrderUseCase = app.container.get(type_=AsyncCreateOrderUseCase)

    # When
    await use_case.execute(customer_name="MultiHandler", total_amount=150.0)

    # Then - Both handlers should be invoked
    first_handler_count = event_recorder.count_by_handler(
        "AsyncOrderEventHandler.on_order_created"
    )
    second_handler_count = event_recorder.count_by_handler(
        "SecondAsyncOrderEventHandler.on_order_created"
    )

    assert first_handler_count == 1
    assert second_handler_count == 1


# === Resilient Dispatch Tests ===


@pytest.mark.asyncio
async def test_handler_exception_expect_other_handlers_continue(
    app: SpakkyApplication,
    event_recorder: EventRecorder,
    collector: AggregateCollector,
) -> None:
    """하나의 핸들러가 예외를 발생시켜도 나머지 핸들러들은 계속 실행됨을 검증한다."""
    # Given
    use_case: AsyncCreateOrderUseCase = app.container.get(type_=AsyncCreateOrderUseCase)

    # When - FailingOrderEventHandler will raise, but others should still run
    await use_case.execute(customer_name="ResilientTest", total_amount=250.0)

    # Then - FailingOrderEventHandler should have been invoked (before raising)
    failing_handler_count = event_recorder.count_by_handler(
        "FailingOrderEventHandler.on_order_created"
    )
    assert failing_handler_count == 1

    # And other handlers should also have been invoked
    async_handler_count = event_recorder.count_by_handler(
        "AsyncOrderEventHandler.on_order_created"
    )
    assert async_handler_count == 1


# === Collector/Aggregate Cleanup Tests ===


@pytest.mark.asyncio
async def test_collector_cleared_after_event_publishing(
    app: SpakkyApplication,
    event_recorder: EventRecorder,
    collector: AggregateCollector,
) -> None:
    """이벤트 발행 후 AggregateCollector가 비워짐을 검증한다."""
    # Given
    use_case: AsyncCreateOrderUseCase = app.container.get(type_=AsyncCreateOrderUseCase)

    # When
    await use_case.execute(customer_name="CleanupTest", total_amount=175.0)

    # Then
    assert len(collector.all()) == 0


@pytest.mark.asyncio
async def test_aggregate_events_cleared_after_publishing(
    app: SpakkyApplication,
    event_recorder: EventRecorder,
    collector: AggregateCollector,
) -> None:
    """이벤트 발행 후 aggregate.events가 비워짐을 검증한다."""
    # Given
    use_case: AsyncCreateOrderUseCase = app.container.get(type_=AsyncCreateOrderUseCase)

    # When
    order = await use_case.execute(
        customer_name="EventsClearedTest", total_amount=125.0
    )

    # Then
    assert len(order.events) == 0
