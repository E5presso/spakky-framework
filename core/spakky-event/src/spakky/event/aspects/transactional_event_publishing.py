"""Transactional event publishing aspect for automatic domain event publishing.

This module provides aspects that automatically publish domain events after
successful transaction completion. The aspect collects aggregates from the
AggregateCollector, extracts their domain events, and publishes them.

Example:
    @Order(100)  # Executes inside TransactionalAspect(@Order(0))
    @AsyncAspect()
    class AsyncTransactionalEventPublishingAspect(IAsyncAspect):
        async def after_returning_async(self, result: Any) -> None:
            # Publish events from collected aggregates
            ...
"""

from inspect import iscoroutinefunction
from typing import Any

from spakky.core.aop.aspect import Aspect, AsyncAspect
from spakky.core.aop.interfaces.aspect import IAspect, IAsyncAspect
from spakky.core.aop.pointcut import AfterRaising, AfterReturning
from spakky.core.pod.annotations.order import Order
from spakky.data.aspects.transactional import Transactional
from spakky.data.persistency.aggregate_collector import AggregateCollector

from spakky.event.event_publisher import (
    IAsyncDomainEventPublisher,
    IDomainEventPublisher,
)


@Order(1)  # Executes inside AsyncTransactionalAspect(@Order(0))
@AsyncAspect()
class AsyncTransactionalEventPublishingAspect(IAsyncAspect):
    """Aspect for automatic domain event publishing in async transactional methods.

    This aspect intercepts async methods decorated with @Transactional and
    automatically publishes domain events after successful transaction completion.
    The aspect executes inside the TransactionalAspect (@Order(0)), ensuring
    events are published within the same transaction.

    Execution flow:
        1. TransactionalAspect (@Order(0)) begins transaction
        2. UseCase logic executes -> repository.save(aggregate) -> collector.collect()
        3. AsyncTransactionalEventPublishingAspect (@Order(100)) publishes events
        4. TransactionalAspect commits or rolls back

    Args:
        collector: Context-scoped collector tracking saved aggregates
        publisher: Publisher for domain events
    """

    _collector: AggregateCollector
    _publisher: IAsyncDomainEventPublisher

    def __init__(
        self,
        collector: AggregateCollector,
        publisher: IAsyncDomainEventPublisher,
    ) -> None:
        """Initialize async transactional event publishing aspect.

        Args:
            collector: Aggregate collector for tracking saved aggregates.
            publisher: Domain event publisher for publishing events.
        """
        self._collector = collector
        self._publisher = publisher

    @AfterReturning(lambda x: Transactional.exists(x) and iscoroutinefunction(x))
    async def after_returning_async(self, result: Any) -> None:
        """Publish domain events after successful UseCase execution.

        This method is called after a @Transactional method successfully completes.
        It extracts all domain events from collected aggregates and publishes them.
        After publishing, it clears the events from aggregates and clears the collector.

        Args:
            result: The return value of the method.
        """
        for aggregate in self._collector.all():
            for event in aggregate.events:
                await self._publisher.publish(event)
            aggregate.clear_events()
        self._collector.clear()

    @AfterRaising(lambda x: Transactional.exists(x) and iscoroutinefunction(x))
    async def after_raising_async(self, error: Exception) -> None:
        """Clean up collector after UseCase failure.

        This method is called when a @Transactional method raises an exception.
        It only clears the collector without publishing events, as the transaction
        will be rolled back.

        Args:
            error: The exception that was raised.
        """
        self._collector.clear()


@Order(1)  # Executes inside TransactionalAspect(@Order(0))
@Aspect()
class TransactionalEventPublishingAspect(IAspect):
    """Aspect for automatic domain event publishing in sync transactional methods.

    This aspect intercepts sync methods decorated with @Transactional and
    automatically publishes domain events after successful transaction completion.
    The aspect executes inside the TransactionalAspect (@Order(0)), ensuring
    events are published within the same transaction.

    Execution flow:
        1. TransactionalAspect (@Order(0)) begins transaction
        2. UseCase logic executes -> repository.save(aggregate) -> collector.collect()
        3. TransactionalEventPublishingAspect (@Order(100)) publishes events
        4. TransactionalAspect commits or rolls back

    Args:
        collector: Context-scoped collector tracking saved aggregates
        publisher: Publisher for domain events
    """

    _collector: AggregateCollector
    _publisher: IDomainEventPublisher

    def __init__(
        self,
        collector: AggregateCollector,
        publisher: IDomainEventPublisher,
    ) -> None:
        """Initialize sync transactional event publishing aspect.

        Args:
            collector: Aggregate collector for tracking saved aggregates.
            publisher: Domain event publisher for publishing events.
        """
        self._collector = collector
        self._publisher = publisher

    @AfterReturning(lambda x: Transactional.exists(x) and not iscoroutinefunction(x))
    def after_returning(self, result: Any) -> None:
        """Publish domain events after successful UseCase execution.

        This method is called after a @Transactional method successfully completes.
        It extracts all domain events from collected aggregates and publishes them.
        After publishing, it clears the events from aggregates and clears the collector.

        Args:
            result: The return value of the method.
        """
        for aggregate in self._collector.all():
            for event in aggregate.events:
                self._publisher.publish(event)
            aggregate.clear_events()
        self._collector.clear()

    @AfterRaising(lambda x: Transactional.exists(x) and not iscoroutinefunction(x))
    def after_raising(self, error: Exception) -> None:
        """Clean up collector after UseCase failure.

        This method is called when a @Transactional method raises an exception.
        It only clears the collector without publishing events, as the transaction
        will be rolled back.

        Args:
            error: The exception that was raised.
        """
        self._collector.clear()
