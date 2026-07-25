"""SQLAlchemy implementation of IOutboxStorage / IAsyncOutboxStorage."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from spakky.core.pod.annotations.pod import Pod
from spakky.outbox.common.config import OutboxConfig
from spakky.outbox.common.message import OutboxMessage
from spakky.outbox.ports.storage import IAsyncOutboxStorage, IOutboxStorage
from typing import override

from spakky.plugins.sqlalchemy.outbox.table import OutboxMessageTable
from spakky.plugins.sqlalchemy.persistency.connection_manager import (
    AsyncConnectionManager,
    ConnectionManager,
)
from spakky.plugins.sqlalchemy.persistency.session_manager import (
    AsyncSessionManager,
    SessionManager,
)
from sqlalchemy import ColumnElement, Row, Select, and_, or_, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session, aliased, sessionmaker

_DEFAULT_CLAIM_TIMEOUT_SECONDS: float = 300.0


def _awaiting_delivery(row: type[OutboxMessageTable]) -> ColumnElement[bool]:
    """Rows still owed to the broker — neither published nor abandoned.

    Ordering within a partition key is defined over this set: an abandoned
    message has been declared undeliverable, so it no longer holds back the
    messages behind it.
    """
    return and_(row.published_at.is_(None), row.abandoned_at.is_(None))


def _claimable_condition(
    max_retry: int,
    claim_cutoff: datetime,
) -> ColumnElement[bool]:
    """Build the filter for rows a relay instance may take from the outbox.

    On top of the plain pending filter (awaiting delivery, retries left, claim
    free or expired), a message carrying a partition key is only offered when
    every older message of that key still awaiting delivery is offerable too. A
    predecessor sitting in another instance's live claim blocks its successors,
    because publishing them would overtake it on the same broker partition.

    The key filter lives in the query rather than in Python so that blocked rows
    never occupy the `LIMIT` window — otherwise one stalled key would crowd out
    healthy messages and starve the whole outbox.
    """
    predecessor = aliased(OutboxMessageTable)
    return and_(
        _awaiting_delivery(OutboxMessageTable),
        OutboxMessageTable.retry_count < max_retry,
        or_(
            OutboxMessageTable.claimed_at.is_(None),
            OutboxMessageTable.claimed_at < claim_cutoff,
        ),
        or_(
            OutboxMessageTable.partition_key.is_(None),
            ~(
                select(predecessor.id)
                .where(predecessor.partition_key == OutboxMessageTable.partition_key)
                .where(_awaiting_delivery(predecessor))
                .where(
                    tuple_(predecessor.created_at, predecessor.id)
                    < tuple_(OutboxMessageTable.created_at, OutboxMessageTable.id)
                )
                .where(predecessor.claimed_at.is_not(None))
                .where(predecessor.claimed_at >= claim_cutoff)
                .exists()
            ),
        ),
    )


def _partition_key_head_ids() -> Select[tuple[str | None, UUID]]:
    """Select the oldest undelivered message id of every partition key.

    Expressed as a correlated `NOT EXISTS` rather than `DISTINCT ON` so that
    every backend evaluates it the same way — SQLAlchemy silently degrades
    `DISTINCT ON` to a plain `DISTINCT` outside PostgreSQL, which would return
    every row of the key and invert the ownership decision built on this.
    Ties on `created_at` are broken by `id` so exactly one row is the head.
    """
    predecessor = aliased(OutboxMessageTable)
    return (
        select(OutboxMessageTable.partition_key, OutboxMessageTable.id)
        .where(_awaiting_delivery(OutboxMessageTable))
        .where(
            ~(
                select(predecessor.id)
                .where(predecessor.partition_key == OutboxMessageTable.partition_key)
                .where(_awaiting_delivery(predecessor))
                .where(
                    tuple_(predecessor.created_at, predecessor.id)
                    < tuple_(OutboxMessageTable.created_at, OutboxMessageTable.id)
                )
                .exists()
            )
        )
    )


def _keys_headed_elsewhere(
    heads: Sequence[Row[tuple[str | None, UUID]]],
    candidates: Sequence[OutboxMessageTable],
) -> set[str | None]:
    """Partition keys whose head row this instance did not lock.

    `SKIP LOCKED` can hand back a later message of a key while another instance
    holds the head in an uncommitted claim — its `claimed_at` is not visible yet,
    so the query filter cannot see it. Comparing the head against the rows this
    transaction actually locked closes that window.
    """
    locked_ids = {row.id for row in candidates}
    return {
        partition_key for partition_key, head_id in heads if head_id not in locked_ids
    }


def _to_message(row: OutboxMessageTable) -> OutboxMessage:
    """Map a persisted row onto the persistence-agnostic Outbox message."""
    return OutboxMessage(
        id=row.id,
        event_name=row.event_name,
        payload=row.payload,
        headers=row.headers,
        partition_key=row.partition_key,
        created_at=row.created_at,
        published_at=row.published_at,
        retry_count=row.retry_count,
        claimed_at=row.claimed_at,
        abandoned_at=row.abandoned_at,
    )


@Pod()
class SqlAlchemyOutboxStorage(IOutboxStorage):
    """Synchronous SQLAlchemy-based Outbox storage implementation.

    - save(): uses the current transactional session (same TX as business data).
    - fetch_pending/mark_published/increment_retry/mark_abandoned: use
      independent sessions.
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

    @override
    def save(self, message: OutboxMessage) -> None:
        row = OutboxMessageTable(
            id=message.id,
            event_name=message.event_name,
            payload=message.payload,
            headers=message.headers,
            partition_key=message.partition_key,
            created_at=message.created_at,
        )
        self._session_manager.session.add(row)
        self._session_manager.session.flush()

    @staticmethod
    def __claimable_ids(
        session: Session,
        candidates: Sequence[OutboxMessageTable],
    ) -> list[UUID]:
        """Drop candidates whose partition key is headed by another instance."""
        partition_keys = {
            row.partition_key for row in candidates if row.partition_key is not None
        }
        if not partition_keys:
            return [row.id for row in candidates]

        heads = session.execute(
            _partition_key_head_ids().where(
                OutboxMessageTable.partition_key.in_(partition_keys)
            )
        ).all()
        headed_elsewhere = _keys_headed_elsewhere(heads, candidates)
        return [
            row.id for row in candidates if row.partition_key not in headed_elsewhere
        ]

    @override
    def fetch_pending(self, limit: int, max_retry: int) -> list[OutboxMessage]:
        now = datetime.now(UTC)
        claim_cutoff = now - timedelta(seconds=self._claim_timeout_seconds)

        with self._session_factory() as session:
            candidates = (
                session.execute(
                    select(OutboxMessageTable)
                    .where(_claimable_condition(max_retry, claim_cutoff))
                    .order_by(OutboxMessageTable.created_at, OutboxMessageTable.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
                .scalars()
                .all()
            )
            claimable_ids = self.__claimable_ids(session, candidates)
            if not claimable_ids:
                session.commit()
                return []

            # Atomic claim: UPDATE with RETURNING
            rows = (
                session.execute(
                    update(OutboxMessageTable)
                    .where(OutboxMessageTable.id.in_(claimable_ids))
                    .values(claimed_at=now)
                    .returning(OutboxMessageTable)
                )
                .scalars()
                .all()
            )
            session.commit()

            return [_to_message(row) for row in rows]

    @override
    def mark_published(self, message_id: UUID) -> None:
        with self._session_factory() as session:
            session.execute(
                update(OutboxMessageTable)
                .where(OutboxMessageTable.id == message_id)
                .values(published_at=datetime.now(UTC))
            )
            session.commit()

    @override
    def increment_retry(self, message_id: UUID) -> None:
        with self._session_factory() as session:
            session.execute(
                update(OutboxMessageTable)
                .where(OutboxMessageTable.id == message_id)
                .values(retry_count=OutboxMessageTable.retry_count + 1)
            )
            session.commit()

    @override
    def mark_abandoned(self, message_id: UUID) -> None:
        with self._session_factory() as session:
            session.execute(
                update(OutboxMessageTable)
                .where(OutboxMessageTable.id == message_id)
                .values(abandoned_at=datetime.now(UTC))
            )
            session.commit()


@Pod()
class AsyncSqlAlchemyOutboxStorage(IAsyncOutboxStorage):
    """Asynchronous SQLAlchemy-based Outbox storage implementation.

    - save(): uses the current transactional session (same TX as business data).
    - fetch_pending/mark_published/increment_retry/mark_abandoned: use
      independent sessions.
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

    @override
    async def save(self, message: OutboxMessage) -> None:
        row = OutboxMessageTable(
            id=message.id,
            event_name=message.event_name,
            payload=message.payload,
            headers=message.headers,
            partition_key=message.partition_key,
            created_at=message.created_at,
        )
        self._session_manager.session.add(row)
        await self._session_manager.session.flush()

    @staticmethod
    async def __claimable_ids(
        session: AsyncSession,
        candidates: Sequence[OutboxMessageTable],
    ) -> list[UUID]:
        """Drop candidates whose partition key is headed by another instance."""
        partition_keys = {
            row.partition_key for row in candidates if row.partition_key is not None
        }
        if not partition_keys:
            return [row.id for row in candidates]

        heads = (
            await session.execute(
                _partition_key_head_ids().where(
                    OutboxMessageTable.partition_key.in_(partition_keys)
                )
            )
        ).all()
        headed_elsewhere = _keys_headed_elsewhere(heads, candidates)
        return [
            row.id for row in candidates if row.partition_key not in headed_elsewhere
        ]

    @override
    async def fetch_pending(self, limit: int, max_retry: int) -> list[OutboxMessage]:
        now = datetime.now(UTC)
        claim_cutoff = now - timedelta(seconds=self._claim_timeout_seconds)

        async with self._session_factory() as session:
            candidates = (
                (
                    await session.execute(
                        select(OutboxMessageTable)
                        .where(_claimable_condition(max_retry, claim_cutoff))
                        .order_by(OutboxMessageTable.created_at, OutboxMessageTable.id)
                        .limit(limit)
                        .with_for_update(skip_locked=True)
                    )
                )
                .scalars()
                .all()
            )
            claimable_ids = await self.__claimable_ids(session, candidates)
            if not claimable_ids:
                await session.commit()
                return []

            # Atomic claim: UPDATE with RETURNING
            rows = (
                (
                    await session.execute(
                        update(OutboxMessageTable)
                        .where(OutboxMessageTable.id.in_(claimable_ids))
                        .values(claimed_at=now)
                        .returning(OutboxMessageTable)
                    )
                )
                .scalars()
                .all()
            )
            await session.commit()

            return [_to_message(row) for row in rows]

    @override
    async def mark_published(self, message_id: UUID) -> None:
        async with self._session_factory() as session:
            await session.execute(
                update(OutboxMessageTable)
                .where(OutboxMessageTable.id == message_id)
                .values(published_at=datetime.now(UTC))
            )
            await session.commit()

    @override
    async def increment_retry(self, message_id: UUID) -> None:
        async with self._session_factory() as session:
            await session.execute(
                update(OutboxMessageTable)
                .where(OutboxMessageTable.id == message_id)
                .values(retry_count=OutboxMessageTable.retry_count + 1)
            )
            await session.commit()

    @override
    async def mark_abandoned(self, message_id: UUID) -> None:
        async with self._session_factory() as session:
            await session.execute(
                update(OutboxMessageTable)
                .where(OutboxMessageTable.id == message_id)
                .values(abandoned_at=datetime.now(UTC))
            )
            await session.commit()
