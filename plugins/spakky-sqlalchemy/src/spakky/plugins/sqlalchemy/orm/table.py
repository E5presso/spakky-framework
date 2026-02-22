from abc import abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar, Generic, Self, get_args, get_origin

from spakky.core.common.mro import generic_mro
from spakky.core.common.types import ObjectT
from spakky.core.pod.annotations.tag import Tag

from spakky.plugins.sqlalchemy.orm.error import AbstractSpakkySqlAlchemyORMError
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase


class AbstractTable(DeclarativeBase, AsyncAttrs, Generic[ObjectT]):
    __abstract__ = True

    @classmethod
    @abstractmethod
    def from_domain(cls, domain: ObjectT) -> Self: ...

    @abstractmethod
    def to_domain(self) -> ObjectT: ...


class CannotUseTableAnnotationError(AbstractSpakkySqlAlchemyORMError):
    message = "The @Table annotation can only be used on classes that inherit from AbstractTable."


class TargetDomainNotSpecifiedError(AbstractSpakkySqlAlchemyORMError):
    message = "The target domain for the @Table annotation is not specified."


@dataclass(eq=False)
class Table(Tag):
    __target_domain_type_sentinel__: ClassVar[type[object]] = type[object]
    domain: type[object] = field(default=__target_domain_type_sentinel__)
    table: type[AbstractTable[object]] = field(init=False)

    def __call__(self, obj: type[ObjectT]) -> type[ObjectT]:
        if not issubclass(obj, AbstractTable):
            raise CannotUseTableAnnotationError(obj)

        if self.domain is self.__target_domain_type_sentinel__:
            table = next(
                (
                    type_
                    for type_ in generic_mro(obj)
                    if get_origin(type_) is AbstractTable
                ),
                None,
            )
            if table is None:  # pragma: no cover
                raise TargetDomainNotSpecifiedError(obj)
            target_domain: type[object] | None = next(iter(get_args(table)), None)
            if target_domain is None:  # pragma: no cover
                raise TargetDomainNotSpecifiedError(obj)
            self.domain = target_domain
        self.table = obj

        return super().__call__(obj)
