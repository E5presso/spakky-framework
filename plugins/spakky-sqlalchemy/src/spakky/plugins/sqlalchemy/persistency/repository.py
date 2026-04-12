from abc import ABC
from typing import Any, Sequence, get_args, get_origin

from spakky.core.common.mro import generic_mro
from spakky.data.persistency.aggregate_collector import AggregateCollector
from spakky.data.persistency.repository import (
    AggregateIdT_contra,
    EntityNotFoundError,
    IAsyncGenericRepository,
    IGenericRepository,
    VersionConflictError,
)
from spakky.domain.models.aggregate_root import AggregateRootT
from typing_extensions import override

from spakky.plugins.sqlalchemy.orm.schema_registry import SchemaRegistry
from spakky.plugins.sqlalchemy.orm.table import AbstractMappableTable
from spakky.plugins.sqlalchemy.persistency.error import (
    AbstractSpakkySqlAlchemyPersistencyError,
)
from spakky.plugins.sqlalchemy.persistency.session_manager import (
    AsyncSessionManager,
    SessionManager,
)
from sqlalchemy import ColumnElement, and_, select, tuple_
from sqlalchemy.exc import NoResultFound
from sqlalchemy.inspection import inspect
from sqlalchemy.orm.exc import StaleDataError


class CannotDetermineAggregateTypeError(AbstractSpakkySqlAlchemyPersistencyError):
    """Raised when aggregate type cannot be resolved from generic parameters."""

    message = "Cannot determine aggregate type from generic parameters"


class AbstractGenericRepository(
    IGenericRepository[AggregateRootT, AggregateIdT_contra], ABC
):
    """Generic repository implementation for SQLAlchemy.

    This class provides basic CRUD operations using SQLAlchemy sessions.
    It serves as a base class for specific entity repositories.
    """

    _aggregate_type: type[AggregateRootT]
    _session_manager: SessionManager
    _schema_registry: SchemaRegistry
    _aggregate_collector: AggregateCollector

    def __init__(
        self,
        session_manager: SessionManager,
        schema_registry: SchemaRegistry,
        aggregate_collector: AggregateCollector,
    ) -> None:
        """Resolve aggregate type from generic parameters and store dependencies."""
        parameterized_base = next(
            (
                type_
                for type_ in generic_mro(type(self))
                if get_origin(type_) is AbstractGenericRepository
            ),
            None,
        )
        if parameterized_base is None:
            raise CannotDetermineAggregateTypeError(type(self))
        self._aggregate_type = next(iter(get_args(parameterized_base)))
        self._session_manager = session_manager
        self._schema_registry = schema_registry
        self._aggregate_collector = aggregate_collector

    def _build_pk_condition(
        self,
        pk_columns: Sequence[Any],  # Any: SQLAlchemy inspect returns untyped PK
        aggregate_id: Any,  # Any: Runtime type varies (UUID, int, tuple, etc.)
    ) -> ColumnElement[bool]:
        """Build a WHERE condition for primary key matching.

        Supports both single-column and composite primary keys.
        For composite PKs, aggregate_id should be a tuple matching
        the order of PK columns.

        Args:
            pk_columns: Primary key columns from SQLAlchemy inspect.
            aggregate_id: Single value or tuple of values for composite PK.

        Returns:
            SQLAlchemy condition expression.
        """
        if len(pk_columns) == 1:
            return pk_columns[0] == aggregate_id
        return and_(*(col == val for col, val in zip(pk_columns, aggregate_id)))

    def _build_pk_in_condition(
        self,
        pk_columns: Sequence[Any],  # Any: SQLAlchemy inspect returns untyped PK
        aggregate_ids: Sequence[
            Any
        ],  # Any: Runtime type varies (UUID, int, tuple, etc.)
    ) -> ColumnElement[bool]:
        """Build a WHERE IN condition for multiple primary key values.

        Supports both single-column and composite primary keys.
        For composite PKs, each aggregate_id should be a tuple.

        Args:
            pk_columns: Primary key columns from SQLAlchemy inspect.
            aggregate_ids: Sequence of values (or tuples for composite PK).

        Returns:
            SQLAlchemy IN condition expression.
        """
        if len(pk_columns) == 1:
            return pk_columns[0].in_(aggregate_ids)
        return tuple_(*pk_columns).in_(aggregate_ids)

    @override
    def get(self, aggregate_id: AggregateIdT_contra) -> AggregateRootT:
        try:
            table = self._schema_registry.get_type(self._aggregate_type)
            pk_columns = inspect(table).primary_key
            result = self._session_manager.session.execute(
                select(table).where(self._build_pk_condition(pk_columns, aggregate_id))
            ).scalar_one()
            return result.to_domain()
        except NoResultFound:
            raise EntityNotFoundError(aggregate_id)

    @override
    def get_or_none(self, aggregate_id: AggregateIdT_contra) -> AggregateRootT | None:
        table = self._schema_registry.get_type(self._aggregate_type)
        pk_columns = inspect(table).primary_key
        result = self._session_manager.session.execute(
            select(table).where(self._build_pk_condition(pk_columns, aggregate_id))
        ).scalar_one_or_none()
        return result.to_domain() if result is not None else None

    @override
    def contains(self, aggregate_id: AggregateIdT_contra) -> bool:
        table = self._schema_registry.get_type(self._aggregate_type)
        pk_columns = inspect(table).primary_key
        result = self._session_manager.session.execute(
            select(pk_columns[0]).where(
                self._build_pk_condition(pk_columns, aggregate_id)
            )
        ).scalar_one_or_none()
        return result is not None

    @override
    def range(
        self, aggregate_ids: Sequence[AggregateIdT_contra]
    ) -> Sequence[AggregateRootT]:
        table = self._schema_registry.get_type(self._aggregate_type)
        pk_columns = inspect(table).primary_key
        results = (
            self._session_manager.session.execute(
                select(table).where(
                    self._build_pk_in_condition(pk_columns, aggregate_ids)
                )
            )
            .scalars()
            .all()
        )
        return [result.to_domain() for result in results]

    @override
    def save(self, aggregate: AggregateRootT) -> AggregateRootT:
        try:
            table = self._schema_registry.from_domain(aggregate)
            merged = self._session_manager.session.merge(table)
            self._session_manager.session.flush()
            self._aggregate_collector.collect(aggregate)
            return merged.to_domain()
        except StaleDataError:
            raise VersionConflictError(aggregate.uid, aggregate.version)

    @override
    def save_all(
        self, aggregates: Sequence[AggregateRootT]
    ) -> Sequence[AggregateRootT]:
        tables: list[AbstractMappableTable[AggregateRootT]] = []
        for aggregate in aggregates:
            try:
                table = self._schema_registry.from_domain(aggregate)
                merged = self._session_manager.session.merge(table)
                tables.append(merged)
            except StaleDataError:
                raise VersionConflictError(aggregate.uid, aggregate.version)
        self._session_manager.session.flush()
        for aggregate in aggregates:
            self._aggregate_collector.collect(aggregate)
        return [table.to_domain() for table in tables]

    @override
    def delete(self, aggregate: AggregateRootT) -> AggregateRootT:
        try:
            table = self._schema_registry.from_domain(aggregate)
            merged = self._session_manager.session.merge(table)
            self._session_manager.session.delete(merged)
            self._session_manager.session.flush()
            self._aggregate_collector.collect(aggregate)
            return merged.to_domain()
        except StaleDataError:
            raise VersionConflictError(aggregate.uid, aggregate.version)

    @override
    def delete_all(
        self, aggregates: Sequence[AggregateRootT]
    ) -> Sequence[AggregateRootT]:
        tables: list[AbstractMappableTable[AggregateRootT]] = []
        for aggregate in aggregates:
            try:
                table = self._schema_registry.from_domain(aggregate)
                merged = self._session_manager.session.merge(table)
                self._session_manager.session.delete(merged)
                tables.append(merged)
            except StaleDataError:
                raise VersionConflictError(aggregate.uid, aggregate.version)
        self._session_manager.session.flush()
        for aggregate in aggregates:
            self._aggregate_collector.collect(aggregate)
        return [table.to_domain() for table in tables]


class AbstractAsyncGenericRepository(
    IAsyncGenericRepository[AggregateRootT, AggregateIdT_contra], ABC
):
    """Async generic repository implementation for SQLAlchemy.

    This class provides basic CRUD operations using SQLAlchemy's async sessions.
    It serves as a base class for specific entity repositories that require async support.
    """

    _aggregate_type: type[AggregateRootT]
    _session_manager: AsyncSessionManager
    _schema_registry: SchemaRegistry
    _aggregate_collector: AggregateCollector

    def __init__(
        self,
        session_manager: AsyncSessionManager,
        schema_registry: SchemaRegistry,
        aggregate_collector: AggregateCollector,
    ) -> None:
        """Resolve aggregate type from generic parameters and store dependencies."""
        parameterized_base = next(
            (
                type_
                for type_ in generic_mro(type(self))
                if get_origin(type_) is AbstractAsyncGenericRepository
            ),
            None,
        )
        if parameterized_base is None:
            raise CannotDetermineAggregateTypeError(type(self))
        self._aggregate_type = next(iter(get_args(parameterized_base)))
        self._session_manager = session_manager
        self._schema_registry = schema_registry
        self._aggregate_collector = aggregate_collector

    def _build_pk_condition(
        self,
        pk_columns: Sequence[Any],  # Any: SQLAlchemy inspect returns untyped PK
        aggregate_id: Any,  # Any: Runtime type varies (UUID, int, tuple, etc.)
    ) -> ColumnElement[bool]:
        """Build a WHERE condition for primary key matching.

        Supports both single-column and composite primary keys.
        For composite PKs, aggregate_id should be a tuple matching
        the order of PK columns.

        Args:
            pk_columns: Primary key columns from SQLAlchemy inspect.
            aggregate_id: Single value or tuple of values for composite PK.

        Returns:
            SQLAlchemy condition expression.
        """
        if len(pk_columns) == 1:
            return pk_columns[0] == aggregate_id
        return and_(*(col == val for col, val in zip(pk_columns, aggregate_id)))

    def _build_pk_in_condition(
        self,
        pk_columns: Sequence[Any],  # Any: SQLAlchemy inspect returns untyped PK
        aggregate_ids: Sequence[
            Any
        ],  # Any: Runtime type varies (UUID, int, tuple, etc.)
    ) -> ColumnElement[bool]:
        """Build a WHERE IN condition for multiple primary key values.

        Supports both single-column and composite primary keys.
        For composite PKs, each aggregate_id should be a tuple.

        Args:
            pk_columns: Primary key columns from SQLAlchemy inspect.
            aggregate_ids: Sequence of values (or tuples for composite PK).

        Returns:
            SQLAlchemy IN condition expression.
        """
        if len(pk_columns) == 1:
            return pk_columns[0].in_(aggregate_ids)
        return tuple_(*pk_columns).in_(aggregate_ids)

    @override
    async def get(self, aggregate_id: AggregateIdT_contra) -> AggregateRootT:
        try:
            table = self._schema_registry.get_type(self._aggregate_type)
            pk_columns = inspect(table).primary_key
            result = (
                await self._session_manager.session.execute(
                    select(table).where(
                        self._build_pk_condition(pk_columns, aggregate_id)
                    )
                )
            ).scalar_one()
            return result.to_domain()
        except NoResultFound:
            raise EntityNotFoundError(aggregate_id)

    @override
    async def get_or_none(
        self, aggregate_id: AggregateIdT_contra
    ) -> AggregateRootT | None:
        table = self._schema_registry.get_type(self._aggregate_type)
        pk_columns = inspect(table).primary_key
        result = (
            await self._session_manager.session.execute(
                select(table).where(self._build_pk_condition(pk_columns, aggregate_id))
            )
        ).scalar_one_or_none()
        return result.to_domain() if result is not None else None

    @override
    async def contains(self, aggregate_id: AggregateIdT_contra) -> bool:
        table = self._schema_registry.get_type(self._aggregate_type)
        pk_columns = inspect(table).primary_key
        result = (
            await self._session_manager.session.execute(
                select(pk_columns[0]).where(
                    self._build_pk_condition(pk_columns, aggregate_id)
                )
            )
        ).scalar_one_or_none()
        return result is not None

    @override
    async def range(
        self, aggregate_ids: Sequence[AggregateIdT_contra]
    ) -> Sequence[AggregateRootT]:
        table = self._schema_registry.get_type(self._aggregate_type)
        pk_columns = inspect(table).primary_key
        results = (
            (
                await self._session_manager.session.execute(
                    select(table).where(
                        self._build_pk_in_condition(pk_columns, aggregate_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        return [result.to_domain() for result in results]

    @override
    async def save(self, aggregate: AggregateRootT) -> AggregateRootT:
        try:
            table = self._schema_registry.from_domain(aggregate)
            merged = await self._session_manager.session.merge(table)
            await self._session_manager.session.flush()
            self._aggregate_collector.collect(aggregate)
            return merged.to_domain()
        except StaleDataError:
            raise VersionConflictError(aggregate.uid, aggregate.version)

    @override
    async def save_all(
        self, aggregates: Sequence[AggregateRootT]
    ) -> Sequence[AggregateRootT]:
        tables: list[AbstractMappableTable[AggregateRootT]] = []
        for aggregate in aggregates:
            try:
                table = self._schema_registry.from_domain(aggregate)
                merged = await self._session_manager.session.merge(table)
                tables.append(merged)
            except StaleDataError:
                raise VersionConflictError(aggregate.uid, aggregate.version)
        await self._session_manager.session.flush()
        for aggregate in aggregates:
            self._aggregate_collector.collect(aggregate)
        return [table.to_domain() for table in tables]

    @override
    async def delete(self, aggregate: AggregateRootT) -> AggregateRootT:
        try:
            table = self._schema_registry.from_domain(aggregate)
            merged = await self._session_manager.session.merge(table)
            await self._session_manager.session.delete(merged)
            await self._session_manager.session.flush()
            self._aggregate_collector.collect(aggregate)
            return merged.to_domain()
        except StaleDataError:
            raise VersionConflictError(aggregate.uid, aggregate.version)

    @override
    async def delete_all(
        self, aggregates: Sequence[AggregateRootT]
    ) -> Sequence[AggregateRootT]:
        tables: list[AbstractMappableTable[AggregateRootT]] = []
        for aggregate in aggregates:
            try:
                table = self._schema_registry.from_domain(aggregate)
                merged = await self._session_manager.session.merge(table)
                await self._session_manager.session.delete(merged)
                tables.append(merged)
            except StaleDataError:
                raise VersionConflictError(aggregate.uid, aggregate.version)
        await self._session_manager.session.flush()
        for aggregate in aggregates:
            self._aggregate_collector.collect(aggregate)
        return [table.to_domain() for table in tables]
