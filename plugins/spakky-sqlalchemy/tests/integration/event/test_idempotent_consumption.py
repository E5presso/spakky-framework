"""Idempotent consumption on PostgreSQL: record and business change share a transaction."""

from uuid import uuid4

from pydantic import TypeAdapter
from spakky.core.application.application import SpakkyApplication
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.event.event_publisher import IAsyncEventPublisher, IEventPublisher
from spakky.event.memory.broker import InMemoryEventBroker, InMemoryMessage
from sqlalchemy import func, select

from spakky.plugins.sqlalchemy.event.table import ProcessedEventTable
from spakky.plugins.sqlalchemy.persistency.transaction import AsyncTransaction
from tests.integration.event.handlers import (
    LedgerEntryTable,
    PaymentCaptured,
    RefundIssued,
)


async def ledger_rows(app: SpakkyApplication, order: str) -> list[tuple[str, str]]:
    transaction = app.container.get(type_=AsyncTransaction)
    async with transaction:
        rows = await transaction.session.execute(
            select(LedgerEntryTable.subscriber, LedgerEntryTable.handler)
            .where(LedgerEntryTable.order == order)
            .order_by(LedgerEntryTable.subscriber, LedgerEntryTable.handler)
        )
        return [(row.subscriber, row.handler) for row in rows]


async def inbox_count(app: SpakkyApplication, event: AbstractIntegrationEvent) -> int:
    transaction = app.container.get(type_=AsyncTransaction)
    async with transaction:
        return (
            await transaction.session.execute(
                select(func.count())
                .select_from(ProcessedEventTable)
                .where(ProcessedEventTable.event_id == event.event_id)
            )
        ).scalar_one()


def redeliver(broker: InMemoryEventBroker, event: AbstractIntegrationEvent) -> None:
    """Publish the same serialized event again, as a broker redelivery would."""
    broker.publish(
        InMemoryMessage(
            event_name=event.event_name,
            payload=TypeAdapter(type(event)).dump_json(event),
            headers={},
        )
    )


async def test_duplicate_delivery_expect_each_handler_writes_once_per_subscriber(
    app: SpakkyApplication,
) -> None:
    """같은 이벤트가 다시 와도 구독자·처리기마다 업무 변경은 한 번만 남는다."""
    broker = app.container.get(type_=InMemoryEventBroker)
    event = PaymentCaptured(order=f"order-{uuid4().hex[:8]}")

    app.container.get(type_=IEventPublisher).publish(event)
    await broker.drain_async()
    redeliver(broker, event)
    await broker.drain_async()

    assert await ledger_rows(app, event.order) == [
        ("ledger", "audit"),
        ("ledger", "post"),
        ("reporting", "post"),
    ]
    assert await inbox_count(app, event) == 3
    assert broker.dead_letters("PaymentCaptured", "ledger") == []


async def test_handler_failure_expect_record_rolled_back_and_only_failed_handler_redriven(
    app: SpakkyApplication,
) -> None:
    """실패한 처리기는 업무 변경과 처리 기록이 함께 되돌려지고, 다시 넣으면 그 처리기만 실행된다."""
    broker = app.container.get(type_=InMemoryEventBroker)
    event = PaymentCaptured(order=f"order-{uuid4().hex[:8]}", fail_after_write=True)

    app.container.get(type_=IEventPublisher).publish(event)
    await broker.drain_async()

    assert await ledger_rows(app, event.order) == [
        ("ledger", "audit"),
        ("reporting", "post"),
    ]
    assert await inbox_count(app, event) == 2
    (entry,) = [
        item
        for item in broker.dead_letters("PaymentCaptured", "ledger")
        if str(event.event_id).encode() in item.message.payload
    ]
    assert entry.dead_letter.attempts == 2
    assert entry.dead_letter.pending == frozenset({"LedgerHandler.post"})
    assert entry.dead_letter.failures[0].exception_type == "LedgerWriteFailedError"


async def test_async_duplicate_and_failure_expect_same_guarantees(
    app: SpakkyApplication,
) -> None:
    """비동기 처리기도 중복은 건너뛰고 실패는 기록과 함께 되돌린다."""
    broker = app.container.get(type_=InMemoryEventBroker)
    publisher = app.container.get(type_=IAsyncEventPublisher)
    done = RefundIssued(order=f"refund-{uuid4().hex[:8]}")
    failing = RefundIssued(order=f"refund-{uuid4().hex[:8]}", fail_after_write=True)

    await publisher.publish(done)
    await publisher.publish(failing)
    await broker.drain_async()
    redeliver(broker, done)
    await broker.drain_async()

    assert await ledger_rows(app, done.order) == [("ledger", "post")]
    assert await inbox_count(app, done) == 1
    assert await ledger_rows(app, failing.order) == []
    assert await inbox_count(app, failing) == 0
