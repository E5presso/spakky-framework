"""Tests for OutboxMessageTable."""

from sqlalchemy import Table

from spakky.plugins.outbox_sqlalchemy.persistency.table import (
    OutboxBase,
    OutboxMessageTable,
)


def test_outbox_message_table_has_correct_tablename() -> None:
    """OutboxMessageTable의 __tablename__이 올바른지 검증한다."""
    assert OutboxMessageTable.__tablename__ == "spakky_event_outbox"


def test_outbox_message_table_has_pending_index() -> None:
    """OutboxMessageTable에 pending 메시지 조회용 인덱스가 있는지 검증한다."""
    assert isinstance(OutboxMessageTable.__table__, Table)
    index_names = {idx.name for idx in OutboxMessageTable.__table__.indexes}
    assert "ix_spakky_event_outbox_pending" in index_names


def test_outbox_base_is_independent_declarative_base() -> None:
    """OutboxBase가 독립적인 DeclarativeBase인지 검증한다."""
    assert hasattr(OutboxBase, "metadata")
    assert OutboxMessageTable.__table__ in OutboxBase.metadata.sorted_tables
