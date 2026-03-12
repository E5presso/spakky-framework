"""Unit tests for Kafka PostProcessor event type validation.

Tests that the Kafka PostProcessor only registers IntegrationEvent handlers
and correctly ignores DomainEvent handlers.
"""

from unittest.mock import Mock

import pytest
from spakky.core.application.application_context import ApplicationContext
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractDomainEvent, AbstractIntegrationEvent
from spakky.event.event_consumer import (
    IAsyncEventConsumer,
    IEventConsumer,
)
from spakky.event.stereotype.event_handler import EventHandler, on_event

from spakky.plugins.kafka.post_processor import KafkaPostProcessor


@immutable
class SampleIntegrationEvent(AbstractIntegrationEvent):
    """Test integration event for testing."""

    message: str


@immutable
class SampleDomainEvent(AbstractDomainEvent):
    """Test domain event for testing."""

    message: str


def test_kafka_post_processor_registers_integration_event_expect_success() -> None:
    """Kafka PostProcessor가 IntegrationEvent 핸들러를 올바르게 등록하는지 검증한다."""

    @EventHandler()
    class SampleEventHandler:
        @on_event(SampleIntegrationEvent)
        def handle_integration_event(self, event: SampleIntegrationEvent) -> None:
            pass

    # Set up mocks
    mock_consumer = Mock(spec=IEventConsumer)
    mock_async_consumer = Mock(spec=IAsyncEventConsumer)
    mock_container = Mock()
    mock_container.get.side_effect = lambda t: (
        mock_consumer
        if t == IEventConsumer
        else mock_async_consumer
        if t == IAsyncEventConsumer
        else None
    )

    mock_context = Mock(spec=ApplicationContext)

    # Create post-processor
    post_processor = KafkaPostProcessor()
    post_processor.set_container(mock_container)
    post_processor.set_application_context(mock_context)

    # Process event handler
    handler_instance = SampleEventHandler()
    post_processor.post_process(handler_instance)

    # Verify that register was called for IntegrationEvent
    mock_consumer.register.assert_called_once()
    call_args = mock_consumer.register.call_args
    assert call_args[0][0] == SampleIntegrationEvent


def test_kafka_post_processor_registers_async_integration_event_expect_success() -> (
    None
):
    """Kafka PostProcessor가 비동기 IntegrationEvent 핸들러를 올바르게 등록하는지 검증한다."""

    @EventHandler()
    class SampleEventHandler:
        @on_event(SampleIntegrationEvent)
        async def handle_integration_event(self, event: SampleIntegrationEvent) -> None:
            pass

    # Set up mocks
    mock_consumer = Mock(spec=IEventConsumer)
    mock_async_consumer = Mock(spec=IAsyncEventConsumer)
    mock_container = Mock()
    mock_container.get.side_effect = lambda t: (
        mock_consumer
        if t == IEventConsumer
        else mock_async_consumer
        if t == IAsyncEventConsumer
        else None
    )

    mock_context = Mock(spec=ApplicationContext)

    # Create post-processor
    post_processor = KafkaPostProcessor()
    post_processor.set_container(mock_container)
    post_processor.set_application_context(mock_context)

    # Process event handler
    handler_instance = SampleEventHandler()
    post_processor.post_process(handler_instance)

    # Verify that register was called for IntegrationEvent on async consumer
    mock_async_consumer.register.assert_called_once()
    call_args = mock_async_consumer.register.call_args
    assert call_args[0][0] == SampleIntegrationEvent


def test_kafka_post_processor_ignores_domain_event_expect_no_registration() -> None:
    """Kafka PostProcessor가 DomainEvent 핸들러를 등록하지 않는지 검증한다.

    EventRoute[AbstractIntegrationEvent] 타입 제약으로 인해
    IntegrationEvent 타입만 PostProcessor에서 처리됨을 확인한다.
    """

    @EventHandler()
    class SampleEventHandler:
        # This should NOT be registered because it's a DomainEvent
        @on_event(SampleDomainEvent)
        def handle_domain_event(self, event: SampleDomainEvent) -> None:
            pass

    # Set up mocks
    mock_consumer = Mock(spec=IEventConsumer)
    mock_async_consumer = Mock(spec=IAsyncEventConsumer)
    mock_container = Mock()
    mock_container.get.side_effect = lambda t: (
        mock_consumer
        if t == IEventConsumer
        else mock_async_consumer
        if t == IAsyncEventConsumer
        else None
    )

    mock_context = Mock(spec=ApplicationContext)

    # Create post-processor
    post_processor = KafkaPostProcessor()
    post_processor.set_container(mock_container)
    post_processor.set_application_context(mock_context)

    # Process event handler
    handler_instance = SampleEventHandler()
    post_processor.post_process(handler_instance)

    # Verify that register was NOT called because DomainEvent is not IntegrationEvent
    mock_consumer.register.assert_not_called()
    mock_async_consumer.register.assert_not_called()


def test_kafka_post_processor_mixed_events_expect_only_integration_registered() -> None:
    """DomainEvent와 혼합된 경우 IntegrationEvent 핸들러만 등록되는지 검증한다."""

    @EventHandler()
    class SampleEventHandler:
        @on_event(SampleIntegrationEvent)
        def handle_integration_event(self, event: SampleIntegrationEvent) -> None:
            pass

        @on_event(SampleDomainEvent)
        def handle_domain_event(self, event: SampleDomainEvent) -> None:
            pass

    # Set up mocks
    mock_consumer = Mock(spec=IEventConsumer)
    mock_async_consumer = Mock(spec=IAsyncEventConsumer)
    mock_container = Mock()
    mock_container.get.side_effect = lambda t: (
        mock_consumer
        if t == IEventConsumer
        else mock_async_consumer
        if t == IAsyncEventConsumer
        else None
    )

    mock_context = Mock(spec=ApplicationContext)

    # Create post-processor
    post_processor = KafkaPostProcessor()
    post_processor.set_container(mock_container)
    post_processor.set_application_context(mock_context)

    # Process event handler
    handler_instance = SampleEventHandler()
    post_processor.post_process(handler_instance)

    # Verify that only IntegrationEvent was registered
    mock_consumer.register.assert_called_once()
    call_args = mock_consumer.register.call_args
    assert call_args[0][0] == SampleIntegrationEvent

    # DomainEvent should not be registered
    mock_async_consumer.register.assert_not_called()


def test_kafka_post_processor_sync_endpoint_invocation_expect_handler_called() -> None:
    """동기 endpoint가 호출되면 컨트롤러 메서드가 실행됨을 검증한다."""
    handler_called = False
    received_event = None

    @EventHandler()
    class SampleEventHandler:
        @on_event(SampleIntegrationEvent)
        def handle_integration_event(self, event: SampleIntegrationEvent) -> None:
            nonlocal handler_called, received_event
            handler_called = True
            received_event = event

    # Set up mocks
    mock_consumer = Mock(spec=IEventConsumer)
    mock_async_consumer = Mock(spec=IAsyncEventConsumer)

    handler_instance = SampleEventHandler()
    mock_container = Mock()

    def get_mock(t: type) -> object:
        if t == IEventConsumer:
            return mock_consumer
        if t == IAsyncEventConsumer:
            return mock_async_consumer
        if t is type(handler_instance):
            return handler_instance
        return None

    mock_container.get.side_effect = get_mock

    mock_context = Mock(spec=ApplicationContext)

    # Create post-processor
    post_processor = KafkaPostProcessor()
    post_processor.set_container(mock_container)
    post_processor.set_application_context(mock_context)

    # Process event handler
    post_processor.post_process(handler_instance)

    # Get the registered endpoint
    mock_consumer.register.assert_called_once()
    call_args = mock_consumer.register.call_args
    registered_endpoint = call_args[0][1]

    # Create a test event
    test_event = SampleIntegrationEvent(message="test")

    # Call the endpoint
    registered_endpoint(test_event)

    # Verify the handler was called
    assert handler_called
    assert received_event is not None
    assert received_event.message == "test"
    mock_context.clear_context.assert_called()


@pytest.mark.asyncio
async def test_kafka_post_processor_async_endpoint_invocation_expect_handler_called() -> (
    None
):
    """비동기 endpoint가 호출되면 컨트롤러 메서드가 실행됨을 검증한다."""
    handler_called = False
    received_event = None

    @EventHandler()
    class SampleAsyncEventHandler:
        @on_event(SampleIntegrationEvent)
        async def handle_integration_event(self, event: SampleIntegrationEvent) -> None:
            nonlocal handler_called, received_event
            handler_called = True
            received_event = event

    # Set up mocks
    mock_consumer = Mock(spec=IEventConsumer)
    mock_async_consumer = Mock(spec=IAsyncEventConsumer)

    handler_instance = SampleAsyncEventHandler()
    mock_container = Mock()

    def get_mock(t: type) -> object:
        if t == IEventConsumer:
            return mock_consumer
        if t == IAsyncEventConsumer:
            return mock_async_consumer
        if t is type(handler_instance):
            return handler_instance
        return None

    mock_container.get.side_effect = get_mock

    mock_context = Mock(spec=ApplicationContext)

    # Create post-processor
    post_processor = KafkaPostProcessor()
    post_processor.set_container(mock_container)
    post_processor.set_application_context(mock_context)

    # Process event handler
    post_processor.post_process(handler_instance)

    # Get the registered async endpoint
    mock_async_consumer.register.assert_called_once()
    call_args = mock_async_consumer.register.call_args
    registered_endpoint = call_args[0][1]

    # Create a test event
    test_event = SampleIntegrationEvent(message="test")

    # Call the async endpoint
    await registered_endpoint(test_event)

    # Verify the handler was called
    assert handler_called
    assert received_event is not None
    assert received_event.message == "test"
    mock_context.clear_context.assert_called()


def test_kafka_post_processor_non_event_handler_class_expect_early_return() -> None:
    """EventHandler가 아닌 클래스는 즉시 반환되어 등록되지 않음을 검증한다."""

    class RegularClass:
        """일반 클래스 (EventHandler 아님)."""

        def some_method(self) -> None:
            pass

    # Set up mocks
    mock_consumer = Mock(spec=IEventConsumer)
    mock_async_consumer = Mock(spec=IAsyncEventConsumer)
    mock_container = Mock()
    mock_container.get.side_effect = lambda t: (
        mock_consumer
        if t == IEventConsumer
        else mock_async_consumer
        if t == IAsyncEventConsumer
        else None
    )

    mock_context = Mock(spec=ApplicationContext)

    # Create post-processor
    post_processor = KafkaPostProcessor()
    post_processor.set_container(mock_container)
    post_processor.set_application_context(mock_context)

    # Process regular class (not an EventHandler)
    regular_instance = RegularClass()
    result = post_processor.post_process(regular_instance)

    # Should return the same instance without registering anything
    assert result is regular_instance
    mock_consumer.register.assert_not_called()
    mock_async_consumer.register.assert_not_called()


def test_kafka_post_processor_handler_with_non_decorated_method_expect_skip() -> None:
    """@on_event 데코레이터가 없는 메서드는 건너뜀을 검증한다."""

    @EventHandler()
    class SampleEventHandler:
        @on_event(SampleIntegrationEvent)
        def handle_event(self, event: SampleIntegrationEvent) -> None:
            pass

        def helper_method(self) -> str:
            """@on_event가 없는 일반 메서드."""
            return "helper"

    # Set up mocks
    mock_consumer = Mock(spec=IEventConsumer)
    mock_async_consumer = Mock(spec=IAsyncEventConsumer)
    mock_container = Mock()
    mock_container.get.side_effect = lambda t: (
        mock_consumer
        if t == IEventConsumer
        else mock_async_consumer
        if t == IAsyncEventConsumer
        else None
    )

    mock_context = Mock(spec=ApplicationContext)

    # Create post-processor
    post_processor = KafkaPostProcessor()
    post_processor.set_container(mock_container)
    post_processor.set_application_context(mock_context)

    # Process event handler
    handler_instance = SampleEventHandler()
    post_processor.post_process(handler_instance)

    # Only the decorated method should be registered
    mock_consumer.register.assert_called_once()
    call_args = mock_consumer.register.call_args
    assert call_args[0][0] == SampleIntegrationEvent
