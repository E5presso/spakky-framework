"""Unit tests for RabbitMQ PostProcessor event type validation.

Tests that the RabbitMQ PostProcessor only registers IntegrationEvent handlers
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
from spakky.tracing.propagator import ITracePropagator

from spakky.plugins.rabbitmq.post_processor import RabbitMQPostProcessor


@immutable
class SampleIntegrationEvent(AbstractIntegrationEvent):
    """Test integration event for testing."""

    message: str


@immutable
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
    mock_context.contains.return_value = False

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
    mock_context.contains.return_value = False

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
    mock_context.contains.return_value = False

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
    mock_context.contains.return_value = False

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


def test_rabbitmq_post_processor_non_event_handler_expect_pod_returned() -> None:
    """EventHandler가 아닌 일반 Pod는 그대로 반환됨을 검증한다."""

    class RegularPod:
        def some_method(self) -> None:
            pass

    post_processor = RabbitMQPostProcessor()
    pod = RegularPod()

    result = post_processor.post_process(pod)

    assert result is pod


def test_rabbitmq_post_processor_method_without_event_route_expect_skipped() -> None:
    """@on_event 없는 메서드는 스킵됨을 검증한다."""

    @EventHandler()
    class SampleEventHandler:
        @on_event(SampleIntegrationEvent)
        def handle_integration_event(self, event: SampleIntegrationEvent) -> None:
            pass

        def regular_method(self) -> None:
            """This method has no @on_event decorator."""
            pass

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
    mock_context.contains.return_value = False

    post_processor = RabbitMQPostProcessor()
    post_processor.set_container(mock_container)
    post_processor.set_application_context(mock_context)

    handler_instance = SampleEventHandler()
    post_processor.post_process(handler_instance)

    # Only IntegrationEvent handler should be registered
    mock_consumer.register.assert_called_once()


def test_rabbitmq_post_processor_sync_endpoint_invocation_expect_handler_called() -> (
    None
):
    """등록된 동기 endpoint가 호출되면 실제 핸들러가 실행됨을 검증한다."""
    handler_called: dict[str, bool | str] = {"value": False, "result": ""}

    @EventHandler()
    class SampleEventHandler:
        @on_event(SampleIntegrationEvent)
        def handle_integration_event(self, event: SampleIntegrationEvent) -> None:
            handler_called["value"] = True
            handler_called["result"] = f"handled: {event.message}"

    captured_endpoint = {"fn": None}

    def capture_register(event_type: type, endpoint: Mock) -> None:
        captured_endpoint["fn"] = endpoint

    mock_consumer = Mock(spec=IEventConsumer)
    mock_consumer.register.side_effect = capture_register
    mock_async_consumer = Mock(spec=IAsyncEventConsumer)

    handler_instance = SampleEventHandler()
    mock_container = Mock()
    mock_container.get.side_effect = lambda t: (
        mock_consumer
        if t == IEventConsumer
        else mock_async_consumer
        if t == IAsyncEventConsumer
        else handler_instance
        if t == SampleEventHandler
        else None
    )

    mock_context = Mock(spec=ApplicationContext)
    mock_context.contains.return_value = False

    post_processor = RabbitMQPostProcessor()
    post_processor.set_container(mock_container)
    post_processor.set_application_context(mock_context)

    post_processor.post_process(handler_instance)

    # Invoke the captured endpoint
    event = SampleIntegrationEvent(message="test")
    assert captured_endpoint["fn"] is not None
    captured_endpoint["fn"](event)

    assert handler_called["value"] is True
    assert handler_called["result"] == "handled: test"
    mock_context.clear_context.assert_called_once()


@pytest.mark.asyncio
async def test_rabbitmq_post_processor_async_endpoint_invocation_expect_handler_called() -> (
    None
):
    """등록된 비동기 endpoint가 호출되면 실제 핸들러가 실행됨을 검증한다."""

    handler_called: dict[str, bool | str] = {"value": False, "result": ""}

    @EventHandler()
    class SampleEventHandler:
        @on_event(SampleIntegrationEvent)
        async def handle_integration_event(self, event: SampleIntegrationEvent) -> None:
            handler_called["value"] = True
            handler_called["result"] = f"handled: {event.message}"

    captured_endpoint = {"fn": None}

    def capture_register(event_type: type, endpoint: Mock) -> None:
        captured_endpoint["fn"] = endpoint

    mock_consumer = Mock(spec=IEventConsumer)
    mock_async_consumer = Mock(spec=IAsyncEventConsumer)
    mock_async_consumer.register.side_effect = capture_register

    handler_instance = SampleEventHandler()
    mock_container = Mock()
    mock_container.get.side_effect = lambda t: (
        mock_consumer
        if t == IEventConsumer
        else mock_async_consumer
        if t == IAsyncEventConsumer
        else handler_instance
        if t == SampleEventHandler
        else None
    )

    mock_context = Mock(spec=ApplicationContext)
    mock_context.contains.return_value = False

    post_processor = RabbitMQPostProcessor()
    post_processor.set_container(mock_container)
    post_processor.set_application_context(mock_context)

    post_processor.post_process(handler_instance)

    # Invoke the captured async endpoint
    event = SampleIntegrationEvent(message="test")
    assert captured_endpoint["fn"] is not None
    await captured_endpoint["fn"](event)

    assert handler_called["value"] is True
    assert handler_called["result"] == "handled: test"
    mock_context.clear_context.assert_called_once()


# ---------------------------------------------------------------------------
# Propagator injection tests
# ---------------------------------------------------------------------------


def test_rabbitmq_post_processor_with_tracing_available_expect_propagator_injected() -> (
    None
):
    """tracing이 가용하면 consumer에 propagator가 주입됨을 검증한다."""

    @EventHandler()
    class SampleEventHandler:
        @on_event(SampleIntegrationEvent)
        def handle_integration_event(self, event: SampleIntegrationEvent) -> None:
            pass

    mock_propagator = Mock(spec=ITracePropagator)
    mock_consumer = Mock()
    mock_async_consumer = Mock()
    mock_container = Mock()
    mock_container.get.side_effect = lambda t: (
        mock_consumer
        if t == IEventConsumer
        else mock_async_consumer
        if t == IAsyncEventConsumer
        else None
    )

    mock_context = Mock(spec=ApplicationContext)
    mock_context.contains.return_value = True
    mock_context.get.return_value = mock_propagator

    post_processor = RabbitMQPostProcessor()
    post_processor.set_container(mock_container)
    post_processor.set_application_context(mock_context)

    handler_instance = SampleEventHandler()
    post_processor.post_process(handler_instance)

    mock_consumer.set_propagator.assert_called_once_with(mock_propagator)
    mock_async_consumer.set_propagator.assert_called_once_with(mock_propagator)


def test_rabbitmq_post_processor_without_tracing_expect_no_propagator_injected() -> (
    None
):
    """tracing��� 미가용하면 set_propagator가 호출되지 않음을 ���증한다."""

    @EventHandler()
    class SampleEventHandler:
        @on_event(SampleIntegrationEvent)
        def handle_integration_event(self, event: SampleIntegrationEvent) -> None:
            pass

    mock_consumer = Mock()
    mock_async_consumer = Mock()
    mock_container = Mock()
    mock_container.get.side_effect = lambda t: (
        mock_consumer
        if t == IEventConsumer
        else mock_async_consumer
        if t == IAsyncEventConsumer
        else None
    )

    mock_context = Mock(spec=ApplicationContext)
    mock_context.contains.return_value = False

    post_processor = RabbitMQPostProcessor()
    post_processor.set_container(mock_container)
    post_processor.set_application_context(mock_context)

    handler_instance = SampleEventHandler()
    post_processor.post_process(handler_instance)

    mock_consumer.set_propagator.assert_not_called()
    mock_async_consumer.set_propagator.assert_not_called()


def test_rabbitmq_post_processor_with_tracing_but_no_set_propagator_expect_skipped() -> (
    None
):
    """consumer에 set_propagator가 없으면 주입을 건너뜀을 검증한다."""

    @EventHandler()
    class SampleEventHandler:
        @on_event(SampleIntegrationEvent)
        def handle_integration_event(self, event: SampleIntegrationEvent) -> None:
            pass

    mock_propagator = Mock(spec=ITracePropagator)
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
    mock_context.contains.return_value = True
    mock_context.get.return_value = mock_propagator

    post_processor = RabbitMQPostProcessor()
    post_processor.set_container(mock_container)
    post_processor.set_application_context(mock_context)

    handler_instance = SampleEventHandler()
    # Should not raise even though consumer lacks set_propagator
    post_processor.post_process(handler_instance)

    assert not hasattr(mock_consumer, "set_propagator")
    assert not hasattr(mock_async_consumer, "set_propagator")
