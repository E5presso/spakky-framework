"""Unit tests for RabbitMQ PostProcessor event type validation.

Tests that the RabbitMQ PostProcessor only registers IntegrationEvent handlers
and correctly ignores DomainEvent handlers.
"""

from unittest.mock import Mock

from spakky.core.application.application_context import ApplicationContext
from spakky.domain.models.event import AbstractDomainEvent, AbstractIntegrationEvent
from spakky.event.event_consumer import (
    IAsyncIntegrationEventConsumer,
    IIntegrationEventConsumer,
)
from spakky.event.stereotype.event_handler import EventHandler, on_event

from spakky.plugins.rabbitmq.post_processor import RabbitMQPostProcessor


class TestIntegrationEvent(AbstractIntegrationEvent):
    """Test integration event for testing."""

    message: str


class TestDomainEvent(AbstractDomainEvent):
    """Test domain event for testing."""

    message: str


def test_rabbitmq_post_processor_registers_integration_event_expect_success() -> None:
    """Test that RabbitMQ PostProcessor registers IntegrationEvent handlers."""

    @EventHandler()
    class TestEventHandler:
        @on_event(TestIntegrationEvent)
        def handle_integration_event(self, event: TestIntegrationEvent) -> None:
            pass

    # Set up mocks
    mock_consumer = Mock(spec=IIntegrationEventConsumer)
    mock_async_consumer = Mock(spec=IAsyncIntegrationEventConsumer)
    mock_container = Mock()
    mock_container.get.side_effect = lambda t: (
        mock_consumer
        if t == IIntegrationEventConsumer
        else mock_async_consumer
        if t == IAsyncIntegrationEventConsumer
        else None
    )

    mock_context = Mock(spec=ApplicationContext)

    # Create post-processor
    post_processor = RabbitMQPostProcessor()
    post_processor.set_container(mock_container)
    post_processor.set_application_context(mock_context)

    # Process event handler
    handler_instance = TestEventHandler()
    post_processor.post_process(handler_instance)

    # Verify that register was called for IntegrationEvent
    mock_consumer.register.assert_called_once()
    call_args = mock_consumer.register.call_args
    assert call_args[0][0] == TestIntegrationEvent


def test_rabbitmq_post_processor_registers_async_integration_event_expect_success() -> (
    None
):
    """Test that RabbitMQ PostProcessor registers async IntegrationEvent handlers."""

    @EventHandler()
    class TestEventHandler:
        @on_event(TestIntegrationEvent)
        async def handle_integration_event(self, event: TestIntegrationEvent) -> None:
            pass

    # Set up mocks
    mock_consumer = Mock(spec=IIntegrationEventConsumer)
    mock_async_consumer = Mock(spec=IAsyncIntegrationEventConsumer)
    mock_container = Mock()
    mock_container.get.side_effect = lambda t: (
        mock_consumer
        if t == IIntegrationEventConsumer
        else mock_async_consumer
        if t == IAsyncIntegrationEventConsumer
        else None
    )

    mock_context = Mock(spec=ApplicationContext)

    # Create post-processor
    post_processor = RabbitMQPostProcessor()
    post_processor.set_container(mock_container)
    post_processor.set_application_context(mock_context)

    # Process event handler
    handler_instance = TestEventHandler()
    post_processor.post_process(handler_instance)

    # Verify that register was called for IntegrationEvent on async consumer
    mock_async_consumer.register.assert_called_once()
    call_args = mock_async_consumer.register.call_args
    assert call_args[0][0] == TestIntegrationEvent


def test_rabbitmq_post_processor_ignores_domain_event_expect_no_registration() -> None:
    """Test that RabbitMQ PostProcessor does NOT register DomainEvent handlers.

    This test verifies the type constraint in EventRoute[AbstractIntegrationEvent]
    which ensures only IntegrationEvent types are processed by the PostProcessor.
    """

    @EventHandler()
    class TestEventHandler:
        # This should NOT be registered because it's a DomainEvent
        @on_event(TestDomainEvent)
        def handle_domain_event(self, event: TestDomainEvent) -> None:
            pass

    # Set up mocks
    mock_consumer = Mock(spec=IIntegrationEventConsumer)
    mock_async_consumer = Mock(spec=IAsyncIntegrationEventConsumer)
    mock_container = Mock()
    mock_container.get.side_effect = lambda t: (
        mock_consumer
        if t == IIntegrationEventConsumer
        else mock_async_consumer
        if t == IAsyncIntegrationEventConsumer
        else None
    )

    mock_context = Mock(spec=ApplicationContext)

    # Create post-processor
    post_processor = RabbitMQPostProcessor()
    post_processor.set_container(mock_container)
    post_processor.set_application_context(mock_context)

    # Process event handler
    handler_instance = TestEventHandler()
    post_processor.post_process(handler_instance)

    # Verify that register was NOT called because DomainEvent is not IntegrationEvent
    mock_consumer.register.assert_not_called()
    mock_async_consumer.register.assert_not_called()


def test_rabbitmq_post_processor_mixed_events_expect_only_integration_registered() -> (
    None
):
    """Test that only IntegrationEvent handlers are registered when mixed with DomainEvents."""

    @EventHandler()
    class TestEventHandler:
        @on_event(TestIntegrationEvent)
        def handle_integration_event(self, event: TestIntegrationEvent) -> None:
            pass

        @on_event(TestDomainEvent)
        def handle_domain_event(self, event: TestDomainEvent) -> None:
            pass

    # Set up mocks
    mock_consumer = Mock(spec=IIntegrationEventConsumer)
    mock_async_consumer = Mock(spec=IAsyncIntegrationEventConsumer)
    mock_container = Mock()
    mock_container.get.side_effect = lambda t: (
        mock_consumer
        if t == IIntegrationEventConsumer
        else mock_async_consumer
        if t == IAsyncIntegrationEventConsumer
        else None
    )

    mock_context = Mock(spec=ApplicationContext)

    # Create post-processor
    post_processor = RabbitMQPostProcessor()
    post_processor.set_container(mock_container)
    post_processor.set_application_context(mock_context)

    # Process event handler
    handler_instance = TestEventHandler()
    post_processor.post_process(handler_instance)

    # Verify that only IntegrationEvent was registered
    mock_consumer.register.assert_called_once()
    call_args = mock_consumer.register.call_args
    assert call_args[0][0] == TestIntegrationEvent

    # DomainEvent should not be registered
    mock_async_consumer.register.assert_not_called()
