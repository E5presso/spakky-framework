from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

from spakky.core.common.mutability import immutable
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)
from spakky.data.aspects.transactional import Transactional
from spakky.data.persistency.transaction import (
    AbstractAsyncTransaction,
    AbstractTransaction,
)
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.event.stereotype.event_handler import EventHandler, on_event


@immutable
class SampleEvent(AbstractIntegrationEvent):
    message: str


@immutable
class AsyncTestEvent(AbstractIntegrationEvent):
    """Event for async handler tests."""

    message: str


@EventHandler()
class DummyEventHandler(IApplicationContextAware):
    __application_context: IApplicationContext
    __count: int
    __context_ids: set[UUID]

    @property
    def count(self) -> int:
        return self.__count

    @property
    def context_ids(self) -> set[UUID]:
        return self.__context_ids

    def __init__(self) -> None:
        self.__count = 0
        self.__context_ids = set()

    def set_application_context(self, application_context: IApplicationContext) -> None:
        self.__application_context = application_context

    @on_event(SampleEvent)
    def handle_sample(self, event: SampleEvent) -> None:
        print(f"Received event: {event}")
        self.__count += 1
        self.__context_ids.add(self.__application_context.get_context_id())


@EventHandler()
class AsyncEventHandler:
    """Handler for testing async event consumption."""

    __application_context: IApplicationContext
    __count: int
    __context_ids: set[UUID]

    @property
    def count(self) -> int:
        return self.__count

    @property
    def context_ids(self) -> set[UUID]:
        return self.__context_ids

    def __init__(self) -> None:
        self.__count = 0
        self.__context_ids = set()

    def set_application_context(self, application_context: IApplicationContext) -> None:
        self.__application_context = application_context

    @on_event(AsyncTestEvent)
    async def handle_async_event(self, event: AsyncTestEvent) -> None:
        print(f"Async handler received event: {event}")
        self.__count += 1
        self.__context_ids.add(self.__application_context.get_context_id())


@immutable
class FanoutEvent(AbstractIntegrationEvent):
    """Event consumed by two independent named subscribers."""

    message: str


@immutable
class PoisonEvent(AbstractIntegrationEvent):
    """Event one subscriber cannot handle while another one can."""

    message: str


@immutable
class BlockingRetryEvent(AbstractIntegrationEvent):
    """Event for blocking retry tests against a real broker."""

    message: str


@immutable
class AsyncBlockingRetryEvent(AbstractIntegrationEvent):
    """Event for async blocking retry tests against a real broker."""

    message: str


@immutable
class DelayedRetryEvent(AbstractIntegrationEvent):
    """Event for delayed retry tests against a real broker."""

    message: str


@immutable
class DelayedDeadLetterEvent(AbstractIntegrationEvent):
    """Event that exhausts delayed retries against a real broker."""

    message: str


@immutable
class SyncRedriveEvent(AbstractIntegrationEvent):
    """Event for synchronous redrive tests against a real broker."""

    message: str


@Pod()
def transaction() -> AbstractTransaction:
    """Transaction double so that TransactionalAspect really advises a handler."""
    return MagicMock(spec=AbstractTransaction)


@Pod()
def async_transaction() -> AbstractAsyncTransaction:
    """Async transaction double required by the async transactional aspect."""
    return AsyncMock(spec=AbstractAsyncTransaction)


@EventHandler(subscriber="billing")
class BillingFanoutHandler:
    """First independent subscriber of FanoutEvent; advised, so its Pod is a proxy."""

    messages: list[str]

    def __init__(self) -> None:
        self.messages = []

    @on_event(FanoutEvent)
    @Transactional()
    def charge(self, event: FanoutEvent) -> None:
        self.messages.append(event.message)


@EventHandler(subscriber="shipping")
class ShippingFanoutHandler:
    """Second independent subscriber of FanoutEvent."""

    messages: list[str]

    def __init__(self) -> None:
        self.messages = []

    @on_event(FanoutEvent)
    def ship(self, event: FanoutEvent) -> None:
        self.messages.append(event.message)


@EventHandler(subscriber="audit")
class AuditPoisonHandler:
    """Healthy subscriber of PoisonEvent."""

    messages: list[str]

    def __init__(self) -> None:
        self.messages = []

    @on_event(PoisonEvent)
    async def record(self, event: PoisonEvent) -> None:
        self.messages.append(event.message)


class BrokenProjectionError(Exception):
    """Failure raised by the broken subscriber until it is healed."""


@EventHandler(subscriber="broken")
class BrokenPoisonHandler:
    """Subscriber of PoisonEvent whose projection and index fail until healed."""

    projection_healthy: bool
    index_healthy: bool
    projected: list[str]
    projection_calls: int
    indexed: list[str]
    index_calls: int
    notified: list[str]

    def __init__(self) -> None:
        self.projection_healthy = False
        self.index_healthy = False
        self.projected = []
        self.projection_calls = 0
        self.indexed = []
        self.index_calls = 0
        self.notified = []

    @on_event(PoisonEvent)
    async def project(self, event: PoisonEvent) -> None:
        self.projection_calls += 1
        if not self.projection_healthy:
            raise BrokenProjectionError("projection store is down")
        self.projected.append(event.message)

    @on_event(PoisonEvent)
    async def index(self, event: PoisonEvent) -> None:
        self.index_calls += 1
        if not self.index_healthy:
            raise BrokenProjectionError("search index is down")
        self.indexed.append(event.message)

    @on_event(PoisonEvent)
    async def notify(self, event: PoisonEvent) -> None:
        self.notified.append(event.message)
