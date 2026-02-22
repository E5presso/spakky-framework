from typing import Any, cast

from spakky.core.common.types import ObjectT
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.aware.tag_registry_aware import ITagRegistryAware
from spakky.core.pod.interfaces.tag_registry import ITagRegistry

from spakky.plugins.sqlalchemy.orm.error import AbstractSpakkySqlAlchemyORMError
from spakky.plugins.sqlalchemy.orm.table import AbstractTable, Table
from sqlalchemy import MetaData
from sqlalchemy import Table as SQLAlchemyTable


class NoSchemaFoundFromDomainError(AbstractSpakkySqlAlchemyORMError):
    message = "No table schema found for given domain"


@Pod()
class SchemaRegistry(ITagRegistryAware):
    _tag_registry: ITagRegistry
    _metadata: MetaData
    _domain_to_table_map: dict[type[Any], type[AbstractTable[Any]]]
    _table_to_domain_map: dict[type[AbstractTable[Any]], type[Any]]

    def __init__(self) -> None:
        self._metadata = MetaData()
        self._domain_to_table_map = {}
        self._table_to_domain_map = {}

    @property
    def metadata(self) -> MetaData:
        """Return MetaData containing only tables registered via @Table tag.

        This filters out tables that were defined but not scanned by the
        SpakkyApplication, ensuring only application-scoped tables are included.

        Returns:
            MetaData with only @Table-tagged tables.
        """
        return self._metadata

    def set_tag_registry(self, tag_registry: ITagRegistry) -> None:
        self._tag_registry = tag_registry
        self._register_table()

    def _register_table(self) -> None:
        for tag in self._tag_registry.tags:
            if not isinstance(tag, Table):
                continue
            table: SQLAlchemyTable = cast(SQLAlchemyTable, tag.table.__table__)
            table.to_metadata(self._metadata)
            self._domain_to_table_map[tag.domain] = tag.table
            self._table_to_domain_map[tag.table] = tag.domain

    def from_domain(self, domain: ObjectT) -> AbstractTable[ObjectT]:
        table: type[AbstractTable[ObjectT]] | None = self._domain_to_table_map.get(
            type(domain)
        )
        if table is None:
            raise NoSchemaFoundFromDomainError(domain)
        return table.from_domain(domain)
