"""Unit tests for RabbitMQ PostProcessor event type validation.

Tests that the RabbitMQ PostProcessor only registers IntegrationEvent handlers
and correctly ignores DomainEvent handlers.
"""

from unittest.mock import Mock

from spakky.core.application.application_context import ApplicationContext
from spakky.domain.models.event import AbstractDomainEvent, AbstractIntegrationEvent
from spakky.event.event_consumer import (
    IAsyncEventConsumer,
    IEventConsumer,
)
from spakky.event.stereotype.event_handler import EventHandler, on_event

from spakky.plugins.rabbitmq.post_processor import RabbitMQPostProcessor


class SampleIntegrationEvent(AbstractIntegrationEvent):
    """Test integration event for testing."""

    message: str


class SampleDomainEvent(AbstractDomainEvent):
    """Test domain event for testing."""

    message: str


def test_rabbitmq_post_processor_registers_integration_event_expect_success() -> None:
    """RabbitMQ PostProcessor가 IntegrationEvent 핸들러를 올바르게 등록하는지 검증한다."""

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
    post_processor = RabbitMQPostProcessor()
    post_processor.set_container(mock_container)
    post_processor.set_application_context(mock_context)

    # Process event handler
    handler_instance = SampleEventHandler()
    post_processor.post_process(handler_instance)

    # Verify that register was called for IntegrationEvent
    mock_consumer.register.assert_called_once()
    call_args = mock_consumer.register.call_args
    assert call_args[0][0] == SampleIntegrationEvent


def test_rabbitmq_post_processor_registers_async_integration_event_expect_success() -> (
    None
):
    """RabbitMQ PostProcessor가 비동기 IntegrationEvent 핸들러를 올바르게 등록하는지 검증한다."""

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
    post_processor = RabbitMQPostProcessor()
    post_processor.set_container(mock_container)
    post_processor.set_application_context(mock_context)

    # Process event handler
    handler_instance = SampleEventHandler()
    post_processor.post_process(handler_instance)

    # Verify that register was called for IntegrationEvent on async consumer
    mock_async_consumer.register.assert_called_once()
    call_args = mock_async_consumer.register.call_args
    assert call_args[0][0] == SampleIntegrationEvent


def test_rabbitmq_post_processor_ignores_domain_event_expect_no_registration() -> None:
    """RabbitMQ PostProcessor가 DomainEvent 핸들러를 등록하지 않는지 검증한다.

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
    post_processor = RabbitMQPostProcessor()
    post_processor.set_container(mock_container)
    post_processor.set_application_context(mock_context)

    # Process event handler
    handler_instance = SampleEventHandler()
    post_processor.post_process(handler_instance)

    # Verify that register was NOT called because DomainEvent is not IntegrationEvent
    mock_consumer.register.assert_not_called()
    mock_async_consumer.register.assert_not_called()


def test_rabbitmq_post_processor_mixed_events_expect_only_integration_registered() -> (
    None
):
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
    post_processor = RabbitMQPostProcessor()
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
