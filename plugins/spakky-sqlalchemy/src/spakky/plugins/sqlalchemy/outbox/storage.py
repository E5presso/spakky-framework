"""SQLAlchemy implementation of IOutboxStorage / IAsyncOutboxStorage."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from spakky.core.pod.annotations.pod import Pod
from spakky.outbox.common.config import OutboxConfig
from spakky.outbox.common.message import OutboxMessage
from spakky.outbox.ports.storage import IAsyncOutboxStorage, IOutboxStorage

from spakky.plugins.sqlalchemy.outbox.table import OutboxMessageTable
from spakky.plugins.sqlalchemy.persistency.connection_manager import (
    AsyncConnectionManager,
    ConnectionManager,
)
from spakky.plugins.sqlalchemy.persistency.session_manager import (
    AsyncSessionManager,
    SessionManager,
)
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import sessionmaker

_DEFAULT_CLAIM_TIMEOUT_SECONDS: float = 300.0


@Pod()
class SqlAlchemyOutboxStorage(IOutboxStorage):
    """Synchronous SQLAlchemy-based Outbox storage implementation.

    - save(): uses the current transactional session (same TX as business data).
    - fetch_pending/mark_published/increment_retry: use independent sessions.
    """

    _session_manager: SessionManager
    _session_factory: sessionmaker
    _claim_timeout_seconds: float

    def __init__(
        self,
        session_manager: SessionManager,
        connection_manager: ConnectionManager,
        config: OutboxConfig | None = None,
    ) -> None:
        self._session_manager = session_manager
        self._session_factory = sessionmaker(
            bind=connection_manager.connection,
            expire_on_commit=False,
        )
        self._claim_timeout_seconds = (
            config.claim_timeout_seconds if config else _DEFAULT_CLAIM_TIMEOUT_SECONDS
        )

    def save(self, message: OutboxMessage) -> None:
        row = OutboxMessageTable(
            id=message.id,
            event_name=message.event_name,
            payload=message.payload,
            headers=message.headers,
            created_at=message.created_at,
        )
        self._session_manager.session.add(row)
        self._session_manager.session.flush()

    def fetch_pending(self, limit: int, max_retry: int) -> list[OutboxMessage]:
        now = datetime.now(UTC)
        claim_cutoff = now - timedelta(seconds=self._claim_timeout_seconds)

        with self._session_factory() as session:
            # Subquery: select IDs with FOR UPDATE SKIP LOCKED
            subq = (
                select(OutboxMessageTable.id)
                .where(OutboxMessageTable.published_at.is_(None))
                .where(OutboxMessageTable.retry_count < max_retry)
                .where(
                    or_(
                        OutboxMessageTable.claimed_at.is_(None),
                        OutboxMessageTable.claimed_at < claim_cutoff,
                    )
                )
                .order_by(OutboxMessageTable.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).scalar_subquery()

            # Atomic claim: UPDATE with RETURNING
            stmt = (
                update(OutboxMessageTable)
                .where(OutboxMessageTable.id.in_(subq))
                .values(claimed_at=now)
                .returning(OutboxMessageTable)
            )
            result = session.execute(stmt)
            rows = result.scalars().all()
            session.commit()

            return [
                OutboxMessage(
                    id=row.id,
                    event_name=row.event_name,
                    payload=row.payload,
                    headers=row.headers,
                    created_at=row.created_at,
                    published_at=row.published_at,
                    retry_count=row.retry_count,
                    claimed_at=row.claimed_at,
                )
                for row in rows
            ]

    def mark_published(self, message_id: UUID) -> None:
        with self._session_factory() as session:
            session.execute(
                update(OutboxMessageTable)
                .where(OutboxMessageTable.id == message_id)
                .values(published_at=datetime.now(UTC))
            )
            session.commit()

    def increment_retry(self, message_id: UUID) -> None:
        with self._session_factory() as session:
            session.execute(
                update(OutboxMessageTable)
                .where(OutboxMessageTable.id == message_id)
                .values(retry_count=OutboxMessageTable.retry_count + 1)
            )
            session.commit()


@Pod()
class AsyncSqlAlchemyOutboxStorage(IAsyncOutboxStorage):
    """Asynchronous SQLAlchemy-based Outbox storage implementation.

    - save(): uses the current transactional session (same TX as business data).
    - fetch_pending/mark_published/increment_retry: use independent sessions.
    """

    _session_manager: AsyncSessionManager
    _session_factory: async_sessionmaker
    _claim_timeout_seconds: float

    def __init__(
        self,
        session_manager: AsyncSessionManager,
        connection_manager: AsyncConnectionManager,
        config: OutboxConfig | None = None,
    ) -> None:
        self._session_manager = session_manager
        self._session_factory = async_sessionmaker(
            bind=connection_manager.connection,
            expire_on_commit=False,
        )
        self._claim_timeout_seconds = (
            config.claim_timeout_seconds if config else _DEFAULT_CLAIM_TIMEOUT_SECONDS
        )

    async def save(self, message: OutboxMessage) -> None:
        row = OutboxMessageTable(
            id=message.id,
            event_name=message.event_name,
            payload=message.payload,
            headers=message.headers,
            created_at=message.created_at,
        )
        self._session_manager.session.add(row)
        await self._session_manager.session.flush()

    async def fetch_pending(self, limit: int, max_retry: int) -> list[OutboxMessage]:
        now = datetime.now(UTC)
        claim_cutoff = now - timedelta(seconds=self._claim_timeout_seconds)

        async with self._session_factory() as session:
            # Subquery: select IDs with FOR UPDATE SKIP LOCKED
            subq = (
                select(OutboxMessageTable.id)
                .where(OutboxMessageTable.published_at.is_(None))
                .where(OutboxMessageTable.retry_count < max_retry)
                .where(
                    or_(
                        OutboxMessageTable.claimed_at.is_(None),
                        OutboxMessageTable.claimed_at < claim_cutoff,
                    )
                )
                .order_by(OutboxMessageTable.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).scalar_subquery()

            # Atomic claim: UPDATE with RETURNING
            stmt = (
                update(OutboxMessageTable)
                .where(OutboxMessageTable.id.in_(subq))
                .values(claimed_at=now)
                .returning(OutboxMessageTable)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
            await session.commit()

            return [
                OutboxMessage(
                    id=row.id,
                    event_name=row.event_name,
                    payload=row.payload,
                    headers=row.headers,
                    created_at=row.created_at,
                    published_at=row.published_at,
                    retry_count=row.retry_count,
                    claimed_at=row.claimed_at,
                )
                for row in rows
            ]

    async def mark_published(self, message_id: UUID) -> None:
        async with self._session_factory() as session:
            await session.execute(
                update(OutboxMessageTable)
                .where(OutboxMessageTable.id == message_id)
                .values(published_at=datetime.now(UTC))
            )
            await session.commit()

    async def increment_retry(self, message_id: UUID) -> None:
        async with self._session_factory() as session:
            await session.execute(
                update(OutboxMessageTable)
                .where(OutboxMessageTable.id == message_id)
                .values(retry_count=OutboxMessageTable.retry_count + 1)
            )
            await session.commit()
