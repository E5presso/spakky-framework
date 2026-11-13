"""Idempotent consumption: a handler processes each event once per subscriber."""

from collections.abc import Callable
from datetime import datetime
from typing import Any

import pytest
from spakky.core.application.application_context import ApplicationContext
from spakky.core.common.mutability import immutable
from spakky.core.pod.annotations.pod import Pod
from spakky.data.aspects.transactional import (
    AsyncTransactionalAspect,
    Transactional,
    TransactionalAspect,
)
from spakky.data.persistency.transaction import (
    AbstractAsyncTransaction,
    AbstractTransaction,
)
from spakky.domain.models.event import AbstractIntegrationEvent

from spakky.event.aspects.idempotent import AsyncIdempotentAspect, IdempotentAspect
from spakky.event.delivery import (
    AsyncSubscriptionDelivery,
    DeliveryCompleted,
    DeliveryDeadLettered,
    DeliveryRetry,
    RetryPolicy,
    SubscriptionDelivery,
)
from spakky.event.error import EventDeliveryContextUnavailableError
from spakky.event.idempotency import (
    IAsyncProcessedEventStore,
    Idempotent,
    IProcessedEventStore,
    ProcessedEventKey,
    ProcessedEventStoreUnavailableError,
    idempotent,
)
from spakky.event.stereotype.event_handler import EventHandler, on_event


@immutable
class OrderPlaced(AbstractIntegrationEvent):
    """An order was placed."""

    order: str


LOG: list[str] = []


def bound(method: Callable[..., Any]) -> Callable[[Any], Any]:
    """Erase the decorator-widened method type; the consumer passes one event."""
    return method


@Pod()
class RecordingTransaction(AbstractTransaction):
    def initialize(self) -> None:
        LOG.append("begin")

    def dispose(self) -> None: ...

    def commit(self) -> None:
        LOG.append("commit")

    def rollback(self) -> None:
        LOG.append("rollback")


@Pod()
class AsyncRecordingTransaction(AbstractAsyncTransaction):
    async def initialize(self) -> None:
        LOG.append("begin")

    async def dispose(self) -> None: ...

    async def commit(self) -> None:
        LOG.append("commit")

    async def rollback(self) -> None:
        LOG.append("rollback")


@Pod()
class MemoryStore(IProcessedEventStore):
    def __init__(self) -> None:
        self.keys: set[ProcessedEventKey] = set()

    def exists(self, key: ProcessedEventKey) -> bool:
        return key in self.keys

    def record(self, key: ProcessedEventKey) -> None:
        LOG.append("record")
        self.keys.add(key)

    def purge(self, older_than: datetime) -> int:
        return 0


@Pod()
class AsyncMemoryStore(IAsyncProcessedEventStore):
    def __init__(self) -> None:
        self.keys: set[ProcessedEventKey] = set()

    async def exists(self, key: ProcessedEventKey) -> bool:
        return key in self.keys

    async def record(self, key: ProcessedEventKey) -> None:
        LOG.append("record")
        self.keys.add(key)

    async def purge(self, older_than: datetime) -> int:
        return 0


@EventHandler(subscriber="billing")
class Billing:
    @on_event(OrderPlaced)
    @Transactional()
    @Idempotent()
    def charge(self, event: OrderPlaced) -> None:
        LOG.append(f"charge:{event.order}")

    @on_event(OrderPlaced)
    @Transactional()
    @idempotent
    def fail(self, event: OrderPlaced) -> None:
        LOG.append(f"fail:{event.order}")
        raise RuntimeError("boom")


@EventHandler(subscriber="billing")
class AsyncBilling:
    @on_event(OrderPlaced)
    @Transactional()
    @Idempotent()
    async def charge(self, event: OrderPlaced) -> None:
        LOG.append(f"charge:{event.order}")


def sync_context(with_store: bool = True) -> ApplicationContext:
    context = ApplicationContext()
    context.add(RecordingTransaction)
    if with_store:
        context.add(MemoryStore)
    context.add(Billing)
    context.add(TransactionalAspect)
    context.add(IdempotentAspect)
    context.start()
    return context


def async_context(with_store: bool = True) -> ApplicationContext:
    context = ApplicationContext()
    context.add(AsyncRecordingTransaction)
    if with_store:
        context.add(AsyncMemoryStore)
    context.add(AsyncBilling)
    context.add(AsyncTransactionalAspect)
    context.add(AsyncIdempotentAspect)
    context.start()
    return context


def test_sync_idempotent_handler_expect_record_inside_transaction_then_skip() -> None:
    """처리 기록은 트랜잭션 안에서 본문보다 먼저 쓰이고, 같은 이벤트는 건너뛴다."""
    LOG.clear()
    context = sync_context()
    handler = context.get(Billing)
    delivery = SubscriptionDelivery(OrderPlaced, "billing", RetryPolicy())
    delivery.add("charge", bound(handler.charge))
    event = OrderPlaced(order="o-1")

    assert delivery.deliver(event) == DeliveryCompleted()
    assert LOG == ["begin", "record", "charge:o-1", "commit"]

    LOG.clear()
    assert delivery.deliver(event) == DeliveryCompleted()
    assert LOG == ["begin", "commit"]
    assert context.get(MemoryStore).keys == {
        ProcessedEventKey(
            subscriber="billing", handler="charge", event_id=event.event_id
        )
    }


def test_sync_idempotent_key_expect_scoped_by_subscriber_and_handler() -> None:
    """같은 이벤트라도 구독자나 처리기가 다르면 각자 한 번씩 처리한다."""
    LOG.clear()
    context = sync_context()
    handler = context.get(Billing)
    event = OrderPlaced(order="o-1")
    for subscriber, name in (
        ("billing", "charge"),
        ("audit", "charge"),
        ("billing", "other"),
    ):
        delivery = SubscriptionDelivery(OrderPlaced, subscriber, RetryPolicy())
        delivery.add(name, bound(handler.charge))
        delivery.deliver(event)
    assert LOG.count("charge:o-1") == 3


def test_sync_idempotent_handler_failure_expect_retry_runs_body_again() -> None:
    """본문이 실패하면 트랜잭션이 되돌려지고 다음 시도에서 다시 실행된다."""
    LOG.clear()
    context = sync_context()
    delivery = SubscriptionDelivery(OrderPlaced, "billing", RetryPolicy(max_attempts=2))
    delivery.add("fail", bound(context.get(Billing).fail))

    outcome = delivery.deliver(OrderPlaced(order="o-1"))

    assert isinstance(outcome, DeliveryRetry)
    assert LOG == ["begin", "record", "fail:o-1", "rollback"]


def test_sync_idempotent_without_store_or_delivery_expect_loud_failure() -> None:
    """저장소나 전달 문맥이 없으면 조용히 통과하지 않고 실패한다."""
    LOG.clear()
    event = OrderPlaced(order="o-1")
    with pytest.raises(EventDeliveryContextUnavailableError):
        sync_context().get(Billing).charge(event)
    delivery = SubscriptionDelivery(OrderPlaced, "billing", RetryPolicy())
    delivery.add("charge", bound(sync_context(with_store=False).get(Billing).charge))
    outcome = delivery.deliver(event)
    assert isinstance(outcome, DeliveryDeadLettered)
    assert outcome.dead_letter.failures[0].exception_type == (
        ProcessedEventStoreUnavailableError.__qualname__
    )
    assert "charge:o-1" not in LOG


async def test_async_idempotent_handler_expect_record_inside_transaction_then_skip() -> (
    None
):
    """비동기 처리기도 트랜잭션 안에서 기록하고 같은 이벤트는 건너뛴다."""
    LOG.clear()
    context = async_context()
    delivery = AsyncSubscriptionDelivery(OrderPlaced, "billing", RetryPolicy())
    delivery.add("charge", bound(context.get(AsyncBilling).charge))
    event = OrderPlaced(order="o-1")

    assert await delivery.deliver(event) == DeliveryCompleted()
    assert LOG == ["begin", "record", "charge:o-1", "commit"]

    LOG.clear()
    assert await delivery.deliver(event) == DeliveryCompleted()
    assert LOG == ["begin", "commit"]


async def test_async_idempotent_without_store_expect_loud_failure() -> None:
    """비동기에서도 저장소가 없으면 실패로 드러난다."""
    LOG.clear()
    delivery = AsyncSubscriptionDelivery(OrderPlaced, "billing", RetryPolicy())
    delivery.add(
        "charge", bound(async_context(with_store=False).get(AsyncBilling).charge)
    )
    outcome = await delivery.deliver(OrderPlaced(order="o-1"))
    assert isinstance(outcome, DeliveryDeadLettered)
    assert outcome.dead_letter.failures[0].exception_type == (
        ProcessedEventStoreUnavailableError.__qualname__
    )
    assert LOG == ["begin", "rollback"]
