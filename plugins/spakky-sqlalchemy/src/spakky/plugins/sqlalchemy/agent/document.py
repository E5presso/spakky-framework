"""Relational storage of agent JSON documents as one typed row per value.

Agent state metadata, signal payloads and evidence payloads are JSON documents.
They are not stored in a JSON or text column. Each scalar, object and array of a
document is one row keyed by its JSON Pointer path, with the scalar value held in a
column of its own type. Saving a document writes only the rows that changed, so an
append-only checkpoint history costs the new rows, not the whole document.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Self

from spakky.agent.types import JsonValue
from sqlalchemy import BigInteger, Boolean, Double, Index, Integer, Text, delete, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from spakky.plugins.sqlalchemy.agent.error import AgentDocumentCorruptedError
from spakky.plugins.sqlalchemy.orm.table import AbstractTable, Table

type DocumentId = str
"""Stable identity of one stored document, such as ``state:<id>:metadata``."""

type JsonPointer = str
"""RFC 6901 JSON Pointer of one value inside a document; the root is ``""``."""


class JsonNodeKind(StrEnum):
    """JSON type of one stored document value."""

    NULL = "null"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    NUMBER = "number"
    TEXT = "text"
    OBJECT = "object"
    ARRAY = "array"


@Table()
class AgentJsonNodeTable(AbstractTable):
    """One value of one agent JSON document."""

    __tablename__ = "spakky_agent_json_node"

    document: Mapped[str] = mapped_column(Text, primary_key=True)
    path: Mapped[str] = mapped_column(Text, primary_key=True)
    parent: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    boolean: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    integer: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    number: Mapped[float | None] = mapped_column(Double, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_spakky_agent_json_node_document", "document"),)


@dataclass(frozen=True, slots=True)
class JsonNode:
    """One value of a document, independent of any SQL session."""

    path: JsonPointer
    parent: JsonPointer | None
    name: str | None
    position: int
    kind: JsonNodeKind
    boolean: bool | None = None
    integer: int | None = None
    number: float | None = None
    text: str | None = None

    @classmethod
    def from_row(cls, row: AgentJsonNodeTable) -> Self:
        """Read one stored row."""
        return cls(
            path=row.path,
            parent=row.parent,
            name=row.name,
            position=row.position,
            kind=JsonNodeKind(row.kind),
            boolean=row.boolean,
            integer=row.integer,
            number=row.number,
            text=row.text,
        )

    def to_row(self, document: DocumentId) -> AgentJsonNodeTable:
        """Build the row that stores this value in ``document``."""
        return AgentJsonNodeTable(
            document=document,
            path=self.path,
            parent=self.parent,
            name=self.name,
            position=self.position,
            kind=self.kind.value,
            boolean=self.boolean,
            integer=self.integer,
            number=self.number,
            text=self.text,
        )


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def encode_document(value: JsonValue) -> tuple[JsonNode, ...]:
    """Decompose one JSON value into its typed rows in document order."""
    nodes: list[JsonNode] = []

    def visit(
        item: JsonValue,
        path: JsonPointer,
        parent: JsonPointer | None,
        name: str | None,
        position: int,
    ) -> None:
        if item is None:
            nodes.append(JsonNode(path, parent, name, position, JsonNodeKind.NULL))
        elif isinstance(item, bool):
            nodes.append(
                JsonNode(
                    path, parent, name, position, JsonNodeKind.BOOLEAN, boolean=item
                )
            )
        elif isinstance(item, int):
            nodes.append(
                JsonNode(
                    path, parent, name, position, JsonNodeKind.INTEGER, integer=item
                )
            )
        elif isinstance(item, float):
            nodes.append(
                JsonNode(path, parent, name, position, JsonNodeKind.NUMBER, number=item)
            )
        elif isinstance(item, str):
            nodes.append(
                JsonNode(path, parent, name, position, JsonNodeKind.TEXT, text=item)
            )
        elif isinstance(item, Mapping):
            nodes.append(JsonNode(path, parent, name, position, JsonNodeKind.OBJECT))
            for index, (key, child) in enumerate(item.items()):
                visit(child, f"{path}/{_escape(key)}", path, key, index)
        else:
            nodes.append(JsonNode(path, parent, name, position, JsonNodeKind.ARRAY))
            for index, child in enumerate(item):
                visit(child, f"{path}/{index}", path, None, index)

    visit(value, "", None, None, 0)
    return tuple(nodes)


def decode_document(nodes: Iterable[JsonNode]) -> JsonValue:
    """Rebuild one JSON value from its rows in any order."""
    children: dict[JsonPointer | None, list[JsonNode]] = {}
    for node in nodes:
        children.setdefault(node.parent, []).append(node)
    roots = children.get(None, [])
    if len(roots) != 1:
        raise AgentDocumentCorruptedError()

    def build(node: JsonNode) -> JsonValue:
        scalars: dict[JsonNodeKind, JsonValue] = {
            JsonNodeKind.NULL: None,
            JsonNodeKind.BOOLEAN: node.boolean,
            JsonNodeKind.INTEGER: node.integer,
            JsonNodeKind.NUMBER: node.number,
            JsonNodeKind.TEXT: node.text,
        }
        if node.kind in scalars:
            return scalars[node.kind]
        ordered = sorted(children.get(node.path, ()), key=lambda child: child.position)
        if node.kind is JsonNodeKind.OBJECT:
            return {str(child.name): build(child) for child in ordered}
        return [build(child) for child in ordered]

    return build(roots[0])


class AgentJsonDocumentStore:
    """Read and write agent JSON documents through one SQL session."""

    def read(self, session: Session, document: DocumentId) -> JsonValue | None:
        """Return one document, or ``None`` when it was never written."""
        return self.read_many(session, (document,)).get(document)

    def read_many(
        self, session: Session, documents: Sequence[DocumentId]
    ) -> dict[DocumentId, JsonValue]:
        """Return every written document among ``documents`` in one query."""
        if not documents:
            return {}
        grouped: dict[DocumentId, list[JsonNode]] = {}
        for row in session.scalars(
            select(AgentJsonNodeTable).where(AgentJsonNodeTable.document.in_(documents))
        ):
            grouped.setdefault(row.document, []).append(JsonNode.from_row(row))
        return {document: decode_document(nodes) for document, nodes in grouped.items()}

    def write(self, session: Session, document: DocumentId, value: JsonValue) -> None:
        """Store ``value`` as ``document``, writing only the rows that changed."""
        desired = {node.path: node for node in encode_document(value)}
        existing = {
            row.path: row
            for row in session.scalars(
                select(AgentJsonNodeTable).where(
                    AgentJsonNodeTable.document == document
                )
            )
        }
        for path, row in existing.items():
            node = desired.get(path)
            if node is None:
                session.delete(row)
            elif JsonNode.from_row(row) != node:
                session.merge(node.to_row(document))
        for path, node in desired.items():
            if path not in existing:
                session.add(node.to_row(document))

    def delete(self, session: Session, document: DocumentId) -> None:
        """Remove every row of ``document``."""
        session.execute(
            delete(AgentJsonNodeTable).where(AgentJsonNodeTable.document == document)
        )
