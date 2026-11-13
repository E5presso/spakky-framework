"""SQLAlchemy implementation of the processed-event store."""

from datetime import UTC, datetime
from typing import override

from spakky.core.pod.annotations.pod import Pod
from spakky.event.error import AbstractSpakkyEventError
from spakky.event.idempotency import (
    IAsyncProcessedEventStore,
    IProcessedEventStore,
    ProcessedEventKey,
)

from spakky.plugins.sqlalchemy.event.table import ProcessedEventTable
from spakky.plugins.sqlalchemy.persistency.session_manager import (
    AsyncSessionManager,
    SessionManager,
)
from sqlalchemy import CursorResult, delete
from sqlalchemy.exc import IntegrityError


class DuplicateProcessedEventError(AbstractSpakkyEventError):
    """Raised when another delivery recorded the same event concurrently.

    The failed insert leaves the transaction unusable, so the handler call is
    abandoned. The consumer retries it, and the retry finds the committed
    record and skips the handler.
    """

    message = "Event is already being processed by a concurrent delivery"
    key: ProcessedEventKey

    def __init__(self, key: ProcessedEventKey) -> None:
        self.key = key
        super().__init__()


@Pod()
class SqlAlchemyProcessedEventStore(IProcessedEventStore):
    """Stores processed-event records through the current scoped session.

    Every method uses the session `@Transactional()` opened for the calling
    handler, so the record commits or rolls back with the handler's changes.
    Without an open transaction the session manager raises
    `SessionNotInitializedError`.
    """

    _session_manager: SessionManager

    def __init__(self, session_manager: SessionManager) -> None:
        self._session_manager = session_manager

    @override
    def exists(self, key: ProcessedEventKey) -> bool:
        """Return whether the handler already processed the event."""
        return (
            self._session_manager.session.get(
                ProcessedEventTable, (key.subscriber, key.handler, key.event_id)
            )
            is not None
        )

    @override
    def record(self, key: ProcessedEventKey) -> None:
        """Insert the record now so a concurrent duplicate fails before effects.

        Raises:
            DuplicateProcessedEventError: The record already exists.
        """
        session = self._session_manager.session
        session.add(
            ProcessedEventTable(
                subscriber=key.subscriber,
                handler=key.handler,
                event_id=key.event_id,
                processed_at=datetime.now(UTC),
            )
        )
        try:
            session.flush()
        except IntegrityError as error:
            raise DuplicateProcessedEventError(key) from error

    @override
    def purge(self, older_than: datetime) -> int:
        """Delete records processed before `older_than` in the current transaction."""
        result = self._session_manager.session.execute(
            delete(ProcessedEventTable).where(
                ProcessedEventTable.processed_at < older_than
            )
        )
        return self._deleted(result)

    def _deleted(self, result: object) -> int:
        # DML 실행 결과만 rowcount를 가진다. execute()의 선언 타입은 그보다 넓다.
        if not isinstance(result, CursorResult):
            return 0
        return result.rowcount


@Pod()
class AsyncSqlAlchemyProcessedEventStore(IAsyncProcessedEventStore):
    """Stores processed-event records through the current scoped async session.

    Follows the same transaction rule as `SqlAlchemyProcessedEventStore`.
    """

    _session_manager: AsyncSessionManager

    def __init__(self, session_manager: AsyncSessionManager) -> None:
        self._session_manager = session_manager

    @override
    async def exists(self, key: ProcessedEventKey) -> bool:
        """Return whether the handler already processed the event."""
        return (
            await self._session_manager.session.get(
                ProcessedEventTable, (key.subscriber, key.handler, key.event_id)
            )
            is not None
        )

    @override
    async def record(self, key: ProcessedEventKey) -> None:
        """Insert the record now so a concurrent duplicate fails before effects.

        Raises:
            DuplicateProcessedEventError: The record already exists.
        """
        session = self._session_manager.session
        session.add(
            ProcessedEventTable(
                subscriber=key.subscriber,
                handler=key.handler,
                event_id=key.event_id,
                processed_at=datetime.now(UTC),
            )
        )
        try:
            await session.flush()
        except IntegrityError as error:
            raise DuplicateProcessedEventError(key) from error

    @override
    async def purge(self, older_than: datetime) -> int:
        """Delete records processed before `older_than` in the current transaction."""
        result = await self._session_manager.session.execute(
            delete(ProcessedEventTable).where(
                ProcessedEventTable.processed_at < older_than
            )
        )
        return self._deleted(result)

    def _deleted(self, result: object) -> int:
        # DML 실행 결과만 rowcount를 가진다. execute()의 선언 타입은 그보다 넓다.
        if not isinstance(result, CursorResult):
            return 0
        return result.rowcount
