"""Event handlers and a ledger table used by the inbox integration scenarios."""

from uuid import UUID, uuid4

from spakky.core.common.mutability import immutable
from spakky.data.aspects.transactional import Transactional
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.event.idempotency import Idempotent
from spakky.event.stereotype.event_handler import EventHandler, on_event
from sqlalchemy.orm import Mapped, mapped_column

from spakky.plugins.sqlalchemy.orm.table import AbstractTable, Table
from spakky.plugins.sqlalchemy.persistency.session_manager import (
    AsyncSessionManager,
    SessionManager,
)


@immutable
class PaymentCaptured(AbstractIntegrationEvent):
    """A payment was captured; consumed by sync handlers."""

    order: str
    fail_after_write: bool = False


@immutable
class RefundIssued(AbstractIntegrationEvent):
    """A refund was issued; consumed by async handlers."""

    order: str
    fail_after_write: bool = False


class LedgerWriteFailedError(Exception):
    """The business write was made but the handler then failed."""


@Table()
class LedgerEntryTable(AbstractTable):
    """Business rows written by the handlers under test."""

    __tablename__ = "inbox_test_ledger"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    subscriber: Mapped[str] = mapped_column()
    handler: Mapped[str] = mapped_column()
    order: Mapped[str] = mapped_column("order_ref")


@EventHandler(subscriber="ledger")
class LedgerHandler:
    """Two idempotent sync handlers in one subscriber."""

    def __init__(self, session_manager: SessionManager) -> None:
        self._session_manager = session_manager

    @on_event(PaymentCaptured)
    @Transactional()
    @Idempotent()
    def post(self, event: PaymentCaptured) -> None:
        self._session_manager.session.add(
            LedgerEntryTable(subscriber="ledger", handler="post", order=event.order)
        )
        self._session_manager.session.flush()
        if event.fail_after_write:
            raise LedgerWriteFailedError()

    @on_event(PaymentCaptured)
    @Transactional()
    @Idempotent()
    def audit(self, event: PaymentCaptured) -> None:
        self._session_manager.session.add(
            LedgerEntryTable(subscriber="ledger", handler="audit", order=event.order)
        )


@EventHandler(subscriber="reporting")
class ReportingHandler:
    """A second subscriber of the same event with its own idempotency scope."""

    def __init__(self, session_manager: SessionManager) -> None:
        self._session_manager = session_manager

    @on_event(PaymentCaptured)
    @Transactional()
    @Idempotent()
    def post(self, event: PaymentCaptured) -> None:
        self._session_manager.session.add(
            LedgerEntryTable(subscriber="reporting", handler="post", order=event.order)
        )


@EventHandler(subscriber="ledger")
class AsyncLedgerHandler:
    """An idempotent async handler."""

    def __init__(self, session_manager: AsyncSessionManager) -> None:
        self._session_manager = session_manager

    @on_event(RefundIssued)
    @Transactional()
    @Idempotent()
    async def post(self, event: RefundIssued) -> None:
        self._session_manager.session.add(
            LedgerEntryTable(subscriber="ledger", handler="post", order=event.order)
        )
        await self._session_manager.session.flush()
        if event.fail_after_write:
            raise LedgerWriteFailedError()
