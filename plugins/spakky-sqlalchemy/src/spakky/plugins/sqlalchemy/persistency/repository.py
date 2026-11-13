from abc import ABC
from typing import Any, get_args, get_origin
from collections.abc import Sequence

from spakky.core.common.mro import generic_mro
from spakky.data.persistency.aggregate_collector import AggregateCollector
from spakky.data.persistency.repository import (
    EntityNotFoundError,
    IAsyncGenericRepository,
    IGenericRepository,
    VersionConflictError,
)
from spakky.domain.models.aggregate_root import AbstractAggregateRoot
from typing import override

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
from sqlalchemy.orm.attributes import set_attribute
from sqlalchemy.orm.exc import StaleDataError


class CannotDetermineAggregateTypeError(AbstractSpakkySqlAlchemyPersistencyError):
    """Raised when aggregate type cannot be resolved from generic parameters."""

    message = "Cannot determine aggregate type from generic parameters"


class AbstractGenericRepository[AggregateRootT: AbstractAggregateRoot, AggregateIdT](
    IGenericRepository[AggregateRootT, AggregateIdT], ABC
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

    def _get_table_type(
        self,
    ) -> type[AbstractMappableTable[AggregateRootT]]:
        return self._schema_registry.get_type(self._aggregate_type)

    def _table_from_domain(
        self, aggregate: AggregateRootT
    ) -> AbstractMappableTable[AggregateRootT]:
        return self._schema_registry.from_domain(aggregate)

    def _version_attribute(
        self, table_type: type[AbstractMappableTable[AggregateRootT]]
    ) -> str | None:
        """Return the ORM attribute mapped to `version_id_col`.

        Args:
            table_type: Table class registered for the aggregate.

        Returns:
            Attribute name, or None when the table is not version-checked
            (None means "optimistic locking does not apply to this table").
        """
        mapper = inspect(table_type)
        if mapper.version_id_col is None:
            return None
        return mapper.get_property_by_column(mapper.version_id_col).key

    def _table_at_persisted_version(
        self, aggregate: AggregateRootT, version_attribute: str | None
    ) -> AbstractMappableTable[AggregateRootT]:
        """Build the table object carrying the version the aggregate was loaded with.

        `merge()` compares this version with the stored row, so a row that
        somebody else changed since the aggregate was loaded is rejected.
        """
        table = self._table_from_domain(aggregate)
        if version_attribute is not None:
            set_attribute(table, version_attribute, aggregate.persisted_version)
        return table

    @override
    def get(self, aggregate_id: AggregateIdT) -> AggregateRootT:
        try:
            table = self._get_table_type()
            pk_columns = inspect(table).primary_key
            result = self._session_manager.session.execute(
                select(table).where(self._build_pk_condition(pk_columns, aggregate_id))
            ).scalar_one()
            return result.to_domain()
        except NoResultFound:
            raise EntityNotFoundError(aggregate_id)

    @override
    def get_or_none(self, aggregate_id: AggregateIdT) -> AggregateRootT | None:
        table = self._get_table_type()
        pk_columns = inspect(table).primary_key
        result = self._session_manager.session.execute(
            select(table).where(self._build_pk_condition(pk_columns, aggregate_id))
        ).scalar_one_or_none()
        return result.to_domain() if result is not None else None

    @override
    def contains(self, aggregate_id: AggregateIdT) -> bool:
        table = self._get_table_type()
        pk_columns = inspect(table).primary_key
        result = self._session_manager.session.execute(
            select(pk_columns[0]).where(
                self._build_pk_condition(pk_columns, aggregate_id)
            )
        ).scalar_one_or_none()
        return result is not None

    @override
    def range(self, aggregate_ids: Sequence[AggregateIdT]) -> Sequence[AggregateRootT]:
        table = self._get_table_type()
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
            version_attribute = self._version_attribute(self._get_table_type())
            table = self._table_at_persisted_version(aggregate, version_attribute)
            merged = self._session_manager.session.merge(table)
            if version_attribute is not None:
                set_attribute(merged, version_attribute, aggregate.version)
            self._session_manager.session.flush()
        except StaleDataError:
            raise VersionConflictError(aggregate.uid, aggregate.version)
        aggregate.mark_persisted()
        self._aggregate_collector.collect(aggregate)
        return merged.to_domain()

    @override
    def save_all(
        self, aggregates: Sequence[AggregateRootT]
    ) -> Sequence[AggregateRootT]:
        version_attribute = self._version_attribute(self._get_table_type())
        tables: list[AbstractMappableTable[AggregateRootT]] = []
        for aggregate in aggregates:
            try:
                table = self._table_at_persisted_version(aggregate, version_attribute)
                merged = self._session_manager.session.merge(table)
                if version_attribute is not None:
                    set_attribute(merged, version_attribute, aggregate.version)
                tables.append(merged)
            except StaleDataError:
                raise VersionConflictError(aggregate.uid, aggregate.version)
        try:
            self._session_manager.session.flush()
        except StaleDataError:
            # The batched flush does not say which row was stale.
            raise VersionConflictError([aggregate.uid for aggregate in aggregates])
        for aggregate in aggregates:
            aggregate.mark_persisted()
            self._aggregate_collector.collect(aggregate)
        return [table.to_domain() for table in tables]

    @override
    def delete(self, aggregate: AggregateRootT) -> AggregateRootT:
        try:
            version_attribute = self._version_attribute(self._get_table_type())
            table = self._table_at_persisted_version(aggregate, version_attribute)
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
        version_attribute = self._version_attribute(self._get_table_type())
        tables: list[AbstractMappableTable[AggregateRootT]] = []
        for aggregate in aggregates:
            try:
                table = self._table_at_persisted_version(aggregate, version_attribute)
                merged = self._session_manager.session.merge(table)
                self._session_manager.session.delete(merged)
                tables.append(merged)
            except StaleDataError:
                raise VersionConflictError(aggregate.uid, aggregate.version)
        try:
            self._session_manager.session.flush()
        except StaleDataError:
            # The batched flush does not say which row was stale.
            raise VersionConflictError([aggregate.uid for aggregate in aggregates])
        for aggregate in aggregates:
            self._aggregate_collector.collect(aggregate)
        return [table.to_domain() for table in tables]


class AbstractAsyncGenericRepository[
    AggregateRootT: AbstractAggregateRoot,
    AggregateIdT,
](IAsyncGenericRepository[AggregateRootT, AggregateIdT], ABC):
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

    def _get_table_type(
        self,
    ) -> type[AbstractMappableTable[AggregateRootT]]:
        return self._schema_registry.get_type(self._aggregate_type)

    def _table_from_domain(
        self, aggregate: AggregateRootT
    ) -> AbstractMappableTable[AggregateRootT]:
        return self._schema_registry.from_domain(aggregate)

    def _version_attribute(
        self, table_type: type[AbstractMappableTable[AggregateRootT]]
    ) -> str | None:
        """Return the ORM attribute mapped to `version_id_col`.

        Args:
            table_type: Table class registered for the aggregate.

        Returns:
            Attribute name, or None when the table is not version-checked
            (None means "optimistic locking does not apply to this table").
        """
        mapper = inspect(table_type)
        if mapper.version_id_col is None:
            return None
        return mapper.get_property_by_column(mapper.version_id_col).key

    def _table_at_persisted_version(
        self, aggregate: AggregateRootT, version_attribute: str | None
    ) -> AbstractMappableTable[AggregateRootT]:
        """Build the table object carrying the version the aggregate was loaded with.

        `merge()` compares this version with the stored row, so a row that
        somebody else changed since the aggregate was loaded is rejected.
        """
        table = self._table_from_domain(aggregate)
        if version_attribute is not None:
            set_attribute(table, version_attribute, aggregate.persisted_version)
        return table

    @override
    async def get(self, aggregate_id: AggregateIdT) -> AggregateRootT:
        try:
            table = self._get_table_type()
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
    async def get_or_none(self, aggregate_id: AggregateIdT) -> AggregateRootT | None:
        table = self._get_table_type()
        pk_columns = inspect(table).primary_key
        result = (
            await self._session_manager.session.execute(
                select(table).where(self._build_pk_condition(pk_columns, aggregate_id))
            )
        ).scalar_one_or_none()
        return result.to_domain() if result is not None else None

    @override
    async def contains(self, aggregate_id: AggregateIdT) -> bool:
        table = self._get_table_type()
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
        self, aggregate_ids: Sequence[AggregateIdT]
    ) -> Sequence[AggregateRootT]:
        table = self._get_table_type()
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
            version_attribute = self._version_attribute(self._get_table_type())
            table = self._table_at_persisted_version(aggregate, version_attribute)
            merged = await self._session_manager.session.merge(table)
            if version_attribute is not None:
                set_attribute(merged, version_attribute, aggregate.version)
            await self._session_manager.session.flush()
        except StaleDataError:
            raise VersionConflictError(aggregate.uid, aggregate.version)
        aggregate.mark_persisted()
        self._aggregate_collector.collect(aggregate)
        return merged.to_domain()

    @override
    async def save_all(
        self, aggregates: Sequence[AggregateRootT]
    ) -> Sequence[AggregateRootT]:
        version_attribute = self._version_attribute(self._get_table_type())
        tables: list[AbstractMappableTable[AggregateRootT]] = []
        for aggregate in aggregates:
            try:
                table = self._table_at_persisted_version(aggregate, version_attribute)
                merged = await self._session_manager.session.merge(table)
                if version_attribute is not None:
                    set_attribute(merged, version_attribute, aggregate.version)
                tables.append(merged)
            except StaleDataError:
                raise VersionConflictError(aggregate.uid, aggregate.version)
        try:
            await self._session_manager.session.flush()
        except StaleDataError:
            # The batched flush does not say which row was stale.
            raise VersionConflictError([aggregate.uid for aggregate in aggregates])
        for aggregate in aggregates:
            aggregate.mark_persisted()
            self._aggregate_collector.collect(aggregate)
        return [table.to_domain() for table in tables]

    @override
    async def delete(self, aggregate: AggregateRootT) -> AggregateRootT:
        try:
            version_attribute = self._version_attribute(self._get_table_type())
            table = self._table_at_persisted_version(aggregate, version_attribute)
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
        version_attribute = self._version_attribute(self._get_table_type())
        tables: list[AbstractMappableTable[AggregateRootT]] = []
        for aggregate in aggregates:
            try:
                table = self._table_at_persisted_version(aggregate, version_attribute)
                merged = await self._session_manager.session.merge(table)
                await self._session_manager.session.delete(merged)
                tables.append(merged)
            except StaleDataError:
                raise VersionConflictError(aggregate.uid, aggregate.version)
        try:
            await self._session_manager.session.flush()
        except StaleDataError:
            # The batched flush does not say which row was stale.
            raise VersionConflictError([aggregate.uid for aggregate in aggregates])
        for aggregate in aggregates:
            self._aggregate_collector.collect(aggregate)
        return [table.to_domain() for table in tables]
