from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Self, get_args, get_origin

from spakky.core.common.mro import generic_mro
from spakky.core.pod.annotations.tag import Tag
from spakky.domain.models.aggregate_root import AbstractAggregateRoot

from spakky.plugins.sqlalchemy.orm.error import AbstractSpakkySqlAlchemyORMError
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, declared_attr

VERSION_COLUMN_NAME = "version"
"""Column name that carries `AbstractAggregateRoot.version` in a mapped table."""


class AbstractTable(DeclarativeBase, AsyncAttrs):
    """Base table class for SQLAlchemy ORM integration with Spakky.

    Use this class for infrastructure tables that don't map to domain models
    (e.g., outbox tables, audit logs). For tables that map to domain entities,
    use AbstractMappableTable instead.
    """

    __abstract__ = True


class AbstractMappableTable[T](AbstractTable):
    """Table class with domain object mapping support.

    Use this class for tables that map to domain entities. Subclasses must
    implement from_domain() and to_domain() methods for bidirectional mapping.
    """

    __abstract__ = True

    @classmethod
    def optimistic_lock_mapper_args(
        cls,
    ) -> dict[str, Any]:  # Any: SQLAlchemy mapper kwargs
        """Build the mapper arguments that enable optimistic locking.

        When the mapped domain type is an `AbstractAggregateRoot` and the table
        has a `version` column, that column becomes the mapper's
        `version_id_col`. The aggregate generates its own version, so
        SQLAlchemy only compares the stored value
        (`version_id_generator=False`) and never generates one.

        Tables of child entities reached through relationships are left
        unversioned: only the aggregate root passes through a repository,
        which is where the loaded version is supplied.

        A subclass that defines its own `__mapper_args__` replaces the default
        as usual in SQLAlchemy declarative mapping.

        Returns:
            Mapper keyword arguments, empty when optimistic locking does not apply.
        """
        mappable = next(
            (
                type_
                for type_ in generic_mro(cls)
                if get_origin(type_) is AbstractMappableTable
            ),
            None,
        )
        domain: object = next(iter(get_args(mappable)), None)
        if not isinstance(domain, type) or not issubclass(
            domain, AbstractAggregateRoot
        ):
            return {}
        version_column = cls.__table__.columns.get(VERSION_COLUMN_NAME)
        if version_column is None:
            return {}
        return {"version_id_col": version_column, "version_id_generator": False}

    # Any: same declaration as DeclarativeBase so subclasses may assign a dict.
    # Evaluated per mapped subclass after its table is built.
    __mapper_args__: Any = declared_attr.directive(
        lambda cls: cls.optimistic_lock_mapper_args()
    )

    @classmethod
    @abstractmethod
    def from_domain(cls, domain: T) -> Self: ...

    @abstractmethod
    def to_domain(self) -> T: ...


class CannotUseTableAnnotationError(AbstractSpakkySqlAlchemyORMError):
    message = "The @Table annotation can only be used on classes that inherit from AbstractTable."


class TargetDomainNotSpecifiedError(AbstractSpakkySqlAlchemyORMError):
    message = "The target domain for the @Table annotation is not specified."


@dataclass(eq=False)
class Table(Tag):
    __target_domain_type_sentinel__: ClassVar[type[object]] = type[object]
    domain: type[object] | None = field(default=__target_domain_type_sentinel__)
    table: type[AbstractTable] = field(init=False)

    def __call__[T: object](self, obj: type[T]) -> type[T]:
        if not issubclass(obj, AbstractTable):
            raise CannotUseTableAnnotationError(obj)

        self.table = obj

        # For AbstractMappableTable subclasses, extract domain type
        if issubclass(obj, AbstractMappableTable):
            if self.domain is self.__target_domain_type_sentinel__:
                table = next(
                    (
                        type_
                        for type_ in generic_mro(obj)
                        if get_origin(type_) is AbstractMappableTable
                    ),
                    None,
                )
                if (
                    table is None
                ):  # pragma: no cover - 방어적 분기, 정상 경로에서 도달 불가
                    raise TargetDomainNotSpecifiedError(obj)
                target_domain: type[object] | None = next(iter(get_args(table)), None)
                if (
                    target_domain is None
                ):  # pragma: no cover - 방어적 분기, 정상 경로에서 도달 불가
                    raise TargetDomainNotSpecifiedError(obj)
                self.domain = target_domain
        else:
            # Non-mappable table
            self.domain = None

        return super().__call__(obj)
