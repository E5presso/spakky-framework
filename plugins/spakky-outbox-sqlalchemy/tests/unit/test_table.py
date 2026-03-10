"""Tests for OutboxMessageTable."""

from spakky.plugins.sqlalchemy.orm.table import AbstractTable, Table
from sqlalchemy import Table as SQLAlchemyTable

from spakky.plugins.outbox_sqlalchemy.persistency.table import OutboxMessageTable


def test_outbox_message_table_has_correct_tablename() -> None:
    """OutboxMessageTable의 __tablename__이 올바른지 검증한다."""
    assert OutboxMessageTable.__tablename__ == "spakky_event_outbox"


def test_outbox_message_table_has_pending_index() -> None:
    """OutboxMessageTable에 pending 메시지 조회용 인덱스가 있는지 검증한다."""
    assert isinstance(OutboxMessageTable.__table__, SQLAlchemyTable)
    index_names = {idx.name for idx in OutboxMessageTable.__table__.indexes}
    assert "ix_spakky_event_outbox_pending" in index_names


def test_outbox_message_table_inherits_abstract_table() -> None:
    """OutboxMessageTable이 AbstractTable을 상속받고 @Table 데코레이터가 적용되었는지 검증한다."""
    assert issubclass(OutboxMessageTable, AbstractTable)
    assert Table.get(OutboxMessageTable).domain is None
    assert Table.get(OutboxMessageTable).table is OutboxMessageTable
