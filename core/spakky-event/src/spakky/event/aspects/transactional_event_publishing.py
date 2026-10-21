"""Transactional event publishing aspect for automatic domain event publishing."""

from inspect import iscoroutinefunction
from typing import Any

from spakky.core.aop.aspect import Aspect, AsyncAspect
from spakky.core.aop.interfaces.aspect import IAspect, IAsyncAspect
from spakky.core.aop.pointcut import After, AfterReturning
from spakky.core.pod.annotations.order import Order
from spakky.data.aspects.transactional import Transactional
from spakky.data.persistency.aggregate_collector import AggregateCollector
from typing import override

from spakky.event.event_publisher import (
    IAsyncEventPublisher,
    IEventPublisher,
)


@Order(0)
@AsyncAspect()
class AsyncTransactionalEventPublishingAspect(IAsyncAspect):
    _collector: AggregateCollector
    _publisher: IAsyncEventPublisher

    def __init__(
        self,
        collector: AggregateCollector,
        publisher: IAsyncEventPublisher,
    ) -> None:
        self._collector = collector
        self._publisher = publisher

    @AfterReturning(lambda x: Transactional.exists(x) and iscoroutinefunction(x))
    @override
    async def after_returning_async(self, result: Any) -> None:
        """Publish domain events from collected aggregates after successful commit."""
        events = {
            event.event_id: event
            for aggregate in self._collector.all()
            for event in aggregate.events
        }
        for aggregate in self._collector.all():
            aggregate.clear_events()
        self._collector.clear()
        for event in events.values():
            await self._publisher.publish(event)

    @After(lambda x: Transactional.exists(x) and iscoroutinefunction(x))
    @override
    async def after_async(self) -> None:
        """Clear the aggregate collector after transaction completion."""
        self._collector.clear()


@Order(0)
@Aspect()
class TransactionalEventPublishingAspect(IAspect):
    _collector: AggregateCollector
    _publisher: IEventPublisher

    def __init__(
        self,
        collector: AggregateCollector,
        publisher: IEventPublisher,
    ) -> None:
        self._collector = collector
        self._publisher = publisher

    @AfterReturning(lambda x: Transactional.exists(x) and not iscoroutinefunction(x))
    @override
    def after_returning(self, result: Any) -> None:
        """Publish domain events from collected aggregates after successful commit."""
        events = {
            event.event_id: event
            for aggregate in self._collector.all()
            for event in aggregate.events
        }
        for aggregate in self._collector.all():
            aggregate.clear_events()
        self._collector.clear()
        for event in events.values():
            self._publisher.publish(event)

    @After(lambda x: Transactional.exists(x) and not iscoroutinefunction(x))
    @override
    def after(self) -> None:
        """Clear the aggregate collector after transaction completion."""
        self._collector.clear()
