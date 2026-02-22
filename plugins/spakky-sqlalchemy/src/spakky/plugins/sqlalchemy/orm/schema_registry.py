from typing import Any

from spakky.core.common.types import ObjectT
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.aware.tag_registry_aware import ITagRegistryAware
from spakky.core.pod.interfaces.tag_registry import ITagRegistry

from spakky.plugins.sqlalchemy.orm.error import AbstractSpakkySqlAlchemyORMError
from spakky.plugins.sqlalchemy.orm.table import AbstractTable, Table


class NoSchemaFoundFromDomainError(AbstractSpakkySqlAlchemyORMError):
    message = "No table schema found for given domain"


@Pod()
class SchemaRegistry(ITagRegistryAware):
    _domain_to_table_map: dict[type[Any], type[AbstractTable[Any]]]
    _table_to_domain_map: dict[type[AbstractTable[Any]], type[Any]]
    _tag_registry: ITagRegistry

    def __init__(self) -> None:
        self._domain_to_table_map = {}
        self._table_to_domain_map = {}

    def set_tag_registry(self, tag_registry: ITagRegistry) -> None:
        self._tag_registry = tag_registry
        self._register_table()

    def _register_table(self) -> None:
        for tag in self._tag_registry.tags:
            if not isinstance(tag, Table):
                continue
            self._domain_to_table_map[tag.domain] = tag.table
            self._table_to_domain_map[tag.table] = tag.domain

    def from_domain(self, domain: ObjectT) -> AbstractTable[ObjectT]:
        table: type[AbstractTable[ObjectT]] | None = self._domain_to_table_map.get(
            type(domain)
        )
        if table is None:
            raise NoSchemaFoundFromDomainError(domain)
        return table.from_domain(domain)
