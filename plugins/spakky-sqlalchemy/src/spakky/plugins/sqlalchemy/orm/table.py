from abc import abstractmethod
from dataclasses import dataclass
from typing import Any, Generic, Self, TypeVar, get_args, get_origin

from spakky.core.common.annotation import ClassAnnotation
from spakky.core.common.mro import generic_mro
from spakky.core.common.types import ObjectT

from spakky.plugins.sqlalchemy.orm.error import AbstractSpakkySqlAlchemyORMError
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase

DomainT = TypeVar("DomainT", bound=Any)


class AbstractTable(DeclarativeBase, AsyncAttrs, Generic[DomainT]):
    __abstract__ = True

    @classmethod
    @abstractmethod
    def from_domain(cls, domain: DomainT) -> Self: ...

    @abstractmethod
    def to_domain(self) -> DomainT: ...


class CannotUseTableAnnotationError(AbstractSpakkySqlAlchemyORMError):
    message = "The @Table annotation can only be used on classes that inherit from AbstractTable."


class TargetDomainNotSpecifiedError(AbstractSpakkySqlAlchemyORMError):
    message = "The target domain for the @Table annotation is not specified."


@dataclass
class Table(ClassAnnotation):
    target_domain: type[object] | None = None

    def __call__(self, obj: type[ObjectT]) -> type[ObjectT]:
        if not issubclass(obj, AbstractTable):
            raise CannotUseTableAnnotationError(obj)

        if self.target_domain is None:
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
            target_domain = next(iter(get_args(table)), None)
            if target_domain is None:  # pragma: no cover
                raise TargetDomainNotSpecifiedError(obj)
            self.target_domain = target_domain

        return super().__call__(obj)
