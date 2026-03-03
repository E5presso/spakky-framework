"""Tests for EventHandlerRegistrationPostProcessor."""

from typing import Callable, overload

from spakky.core.common.mutability import immutable
from spakky.core.common.types import ObjectT
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.container import IContainer
from spakky.domain.models.event import AbstractDomainEvent, AbstractIntegrationEvent

from spakky.event.event_consumer import IAsyncDomainEventConsumer, IDomainEventConsumer
from spakky.event.post_processor import EventHandlerRegistrationPostProcessor
from spakky.event.stereotype.event_handler import EventHandler, on_event


@immutable
class TestDomainEvent(AbstractDomainEvent):
    """Test domain event."""

    message: str


@immutable
class AnotherDomainEvent(AbstractDomainEvent):
    """Another test domain event."""

    value: int


@immutable
class NonDomainEvent(AbstractIntegrationEvent):
    """Non-domain event (integration event)."""

    data: str


class InMemorySyncConsumer(IDomainEventConsumer):
    """In-memory synchronous consumer for testing."""

    def __init__(self) -> None:
        self.registrations: list[tuple[type[AbstractDomainEvent], object]] = []

    def register(self, event: type[AbstractDomainEvent], handler: object) -> None:
        self.registrations.append((event, handler))


class InMemoryAsyncConsumer(IAsyncDomainEventConsumer):
    """In-memory asynchronous consumer for testing."""

    def __init__(self) -> None:
        self.registrations: list[tuple[type[AbstractDomainEvent], object]] = []

    def register(self, event: type[AbstractDomainEvent], handler: object) -> None:
        self.registrations.append((event, handler))


class InMemoryContainer(IContainer):
    """Mock container for testing."""

    def __init__(
        self,
        sync_consumer: IDomainEventConsumer,
        async_consumer: IAsyncDomainEventConsumer,
    ) -> None:
        self._sync_consumer = sync_consumer
        self._async_consumer = async_consumer

    @property
    def pods(self) -> dict[str, Pod]:
        """Not implemented for testing."""
        return {}

    def add(self, obj: object) -> None:
        """Not implemented for testing."""
        pass

    @overload
    def get(self, type_: type[ObjectT]) -> ObjectT: ...

    @overload
    def get(self, type_: type[ObjectT], name: str) -> ObjectT: ...

    def get(
        self,
        type_: type[ObjectT],
        name: str | None = None,
    ) -> ObjectT:
        """Get consumer based on type."""
        if type_ is IDomainEventConsumer:
            return self._sync_consumer  # type: ignore[return-value]
        if type_ is IAsyncDomainEventConsumer:
            return self._async_consumer  # type: ignore[return-value]
        raise ValueError(f"Unexpected type: {type_}")

    def contains(self, type_: type, name: str | None = None) -> bool:
        """Not implemented for testing."""
        return False

    def find(self, selector: Callable[[Pod], bool]) -> set[object]:
        """Not implemented for testing."""
        return set()

    def register(
        self, pod_type: type[object], pod: object, name: str | None = None
    ) -> None:
        """Not implemented for testing."""
        pass


@EventHandler()
class SyncTestEventHandler:
    """Test sync event handler."""

    @on_event(TestDomainEvent)
    def handle_test(self, event: TestDomainEvent) -> None:
        """Handle test domain event."""
        ...

    def non_decorated(self, event: TestDomainEvent) -> None:
        """Non-decorated method (should be ignored)."""
        ...


@EventHandler()
class AsyncTestEventHandler:
    """Test async event handler."""

    @on_event(TestDomainEvent)
    async def handle_test(self, event: TestDomainEvent) -> None:
        """Handle test domain event asynchronously."""
        ...


@EventHandler()
class MultiEventHandler:
    """Event handler with multiple event handlers."""

    @on_event(TestDomainEvent)
    async def handle_test(self, event: TestDomainEvent) -> None:
        """Handle test domain event."""
        ...

    @on_event(AnotherDomainEvent)
    async def handle_another(self, event: AnotherDomainEvent) -> None:
        """Handle another domain event."""
        ...

    async def regular_method(self) -> None:
        """Regular method without @on_event decorator (should be ignored)."""
        ...


@EventHandler()
class NonDomainEventHandler:
    """Event handler with non-domain event (should be ignored)."""

    @on_event(NonDomainEvent)
    async def handle_non_domain(self, event: NonDomainEvent) -> None:
        """Handle non-domain event (should be ignored by PostProcessor)."""
        ...


def test_post_processor_registers_sync_handler_methods() -> None:
    """Test that sync handler methods are registered with sync consumer."""
    sync_consumer = InMemorySyncConsumer()
    async_consumer = InMemoryAsyncConsumer()
    container = InMemoryContainer(sync_consumer, async_consumer)

    post_processor = EventHandlerRegistrationPostProcessor()
    post_processor.set_container(container)

    handler_instance = SyncTestEventHandler()
    post_processor.post_process(handler_instance)

    assert len(sync_consumer.registrations) == 1
    assert sync_consumer.registrations[0][0] is TestDomainEvent
    assert len(async_consumer.registrations) == 0


def test_post_processor_ignore_non_decorated_methods() -> None:
    """Test that non-decorated methods are ignored."""
    sync_consumer = InMemorySyncConsumer()
    async_consumer = InMemoryAsyncConsumer()
    container = InMemoryContainer(sync_consumer, async_consumer)

    post_processor = EventHandlerRegistrationPostProcessor()
    post_processor.set_container(container)

    handler_instance = SyncTestEventHandler()
    post_processor.post_process(handler_instance)

    # Only one decorated method should be registered
    assert len(sync_consumer.registrations) == 1
    assert sync_consumer.registrations[0][0] is TestDomainEvent


def test_post_processor_registers_async_handler_methods() -> None:
    """Test that async handler methods are registered with async consumer."""
    sync_consumer = InMemorySyncConsumer()
    async_consumer = InMemoryAsyncConsumer()
    container = InMemoryContainer(sync_consumer, async_consumer)

    post_processor = EventHandlerRegistrationPostProcessor()
    post_processor.set_container(container)

    handler_instance = AsyncTestEventHandler()
    post_processor.post_process(handler_instance)

    assert len(async_consumer.registrations) == 1
    assert async_consumer.registrations[0][0] is TestDomainEvent
    assert len(sync_consumer.registrations) == 0


def test_post_processor_registers_multiple_event_handlers() -> None:
    """Test that handlers with multiple events register all of them."""
    sync_consumer = InMemorySyncConsumer()
    async_consumer = InMemoryAsyncConsumer()
    container = InMemoryContainer(sync_consumer, async_consumer)

    post_processor = EventHandlerRegistrationPostProcessor()
    post_processor.set_container(container)

    handler_instance = MultiEventHandler()
    post_processor.post_process(handler_instance)

    assert len(async_consumer.registrations) == 2
    event_types = {reg[0] for reg in async_consumer.registrations}
    assert TestDomainEvent in event_types
    assert AnotherDomainEvent in event_types


def test_post_processor_ignores_non_event_handler_objects() -> None:
    """Test that non-EventHandler objects are ignored."""
    sync_consumer = InMemorySyncConsumer()
    async_consumer = InMemoryAsyncConsumer()
    container = InMemoryContainer(sync_consumer, async_consumer)

    post_processor = EventHandlerRegistrationPostProcessor()
    post_processor.set_container(container)

    class NotAnEventHandler:
        def some_method(self) -> None: ...

    obj = NotAnEventHandler()
    post_processor.post_process(obj)

    assert len(sync_consumer.registrations) == 0
    assert len(async_consumer.registrations) == 0


def test_post_processor_ignores_non_domain_event_handlers() -> None:
    """Test that handlers with non-domain events are ignored."""
    sync_consumer = InMemorySyncConsumer()
    async_consumer = InMemoryAsyncConsumer()
    container = InMemoryContainer(sync_consumer, async_consumer)

    post_processor = EventHandlerRegistrationPostProcessor()
    post_processor.set_container(container)

    handler_instance = NonDomainEventHandler()
    post_processor.post_process(handler_instance)

    assert len(sync_consumer.registrations) == 0
    assert len(async_consumer.registrations) == 0
