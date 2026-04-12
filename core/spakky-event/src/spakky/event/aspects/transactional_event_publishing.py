"""Transactional event publishing aspect for automatic domain event publishing."""

from inspect import iscoroutinefunction
from typing import Any

from spakky.core.aop.aspect import Aspect, AsyncAspect
from spakky.core.aop.interfaces.aspect import IAspect, IAsyncAspect
from spakky.core.aop.pointcut import After, AfterReturning
from spakky.core.pod.annotations.order import Order
from spakky.data.aspects.transactional import Transactional
from spakky.data.persistency.aggregate_collector import AggregateCollector
from typing_extensions import override

from spakky.event.event_publisher import (
    IAsyncEventPublisher,
    IEventPublisher,
)


@Order(1)
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
        for aggregate in self._collector.all():
            for event in aggregate.events:
                await self._publisher.publish(event)
            aggregate.clear_events()

    @After(lambda x: Transactional.exists(x) and iscoroutinefunction(x))
    @override
    async def after_async(self) -> None:
        """Clear the aggregate collector after transaction completion."""
        self._collector.clear()


@Order(1)
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
        for aggregate in self._collector.all():
            for event in aggregate.events:
                self._publisher.publish(event)
            aggregate.clear_events()

    @After(lambda x: Transactional.exists(x) and not iscoroutinefunction(x))
    @override
    def after(self) -> None:
        """Clear the aggregate collector after transaction completion."""
        self._collector.clear()
