"""Transactional event publishing aspect for automatic domain event publishing."""

from inspect import iscoroutinefunction
from typing import Any

from spakky.core.aop.aspect import Aspect, AsyncAspect
from spakky.core.aop.interfaces.aspect import IAspect, IAsyncAspect
from spakky.core.aop.pointcut import After, AfterReturning
from spakky.core.pod.annotations.order import Order
from spakky.data.aspects.transactional import Transactional
from spakky.data.persistency.aggregate_collector import AggregateCollector

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
    async def after_returning_async(self, result: Any) -> None:
        for aggregate in self._collector.all():
            for event in aggregate.events:
                await self._publisher.publish(event)
            aggregate.clear_events()

    @After(lambda x: Transactional.exists(x) and iscoroutinefunction(x))
    async def after_async(self) -> None:
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
    def after_returning(self, result: Any) -> None:
        for aggregate in self._collector.all():
            for event in aggregate.events:
                self._publisher.publish(event)
            aggregate.clear_events()

    @After(lambda x: Transactional.exists(x) and not iscoroutinefunction(x))
    def after(self) -> None:
        self._collector.clear()
