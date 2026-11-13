"""Aspects that skip integration events a handler has already processed."""

from inspect import iscoroutinefunction
from logging import getLogger
from typing import Any, override

from spakky.core.aop.aspect import Aspect, AsyncAspect
from spakky.core.aop.interfaces.aspect import IAspect, IAsyncAspect
from spakky.core.aop.pointcut import Around
from spakky.core.common.types import AsyncFunc, Func
from spakky.core.pod.annotations.order import Order
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.container import IContainer

from spakky.event.delivery import EventDeliveryContext
from spakky.event.idempotency import (
    IAsyncProcessedEventStore,
    Idempotent,
    IProcessedEventStore,
    ProcessedEventKey,
    ProcessedEventStoreUnavailableError,
)

logger = getLogger(__name__)

IDEMPOTENT_ASPECT_ORDER = 2
"""Runs inside `TransactionalAspect` (order 1) so the record joins its transaction."""


@Order(IDEMPOTENT_ASPECT_ORDER)
@AsyncAspect()
class AsyncIdempotentAspect(IAsyncAspect, IContainerAware):
    """Skips an async handler call for an event that handler already processed."""

    _container: IContainer

    @override
    def set_container(self, container: IContainer) -> None:
        """Keep the container so the store is resolved only when a handler needs it."""
        self._container = container

    @Around(lambda x: Idempotent.exists(x) and iscoroutinefunction(x))
    @override
    async def around_async(
        self, joinpoint: AsyncFunc, *args: Any, **kwargs: Any
    ) -> Any:
        store = self._container.get_or_none(IAsyncProcessedEventStore)
        if store is None:
            raise ProcessedEventStoreUnavailableError()
        delivery = EventDeliveryContext.current()
        key = ProcessedEventKey(
            subscriber=delivery.subscriber,
            handler=delivery.handler,
            event_id=delivery.event_id,
        )
        if await store.exists(key):
            logger.info(
                f"Skipping event {key.event_id} already processed by "
                f"{key.handler} (subscriber {key.subscriber!r})"
            )
            return None
        await store.record(key)
        return await joinpoint(*args, **kwargs)


@Order(IDEMPOTENT_ASPECT_ORDER)
@Aspect()
class IdempotentAspect(IAspect, IContainerAware):
    """Skips a sync handler call for an event that handler already processed."""

    _container: IContainer

    @override
    def set_container(self, container: IContainer) -> None:
        """Keep the container so the store is resolved only when a handler needs it."""
        self._container = container

    @Around(lambda x: Idempotent.exists(x) and not iscoroutinefunction(x))
    @override
    def around(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:
        store = self._container.get_or_none(IProcessedEventStore)
        if store is None:
            raise ProcessedEventStoreUnavailableError()
        delivery = EventDeliveryContext.current()
        key = ProcessedEventKey(
            subscriber=delivery.subscriber,
            handler=delivery.handler,
            event_id=delivery.event_id,
        )
        if store.exists(key):
            logger.info(
                f"Skipping event {key.event_id} already processed by "
                f"{key.handler} (subscriber {key.subscriber!r})"
            )
            return None
        store.record(key)
        return joinpoint(*args, **kwargs)
