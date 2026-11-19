"""AggregateCollector의 transaction 단위 buffer를 검증한다."""

from unittest.mock import MagicMock

import pytest
from spakky.domain.models.aggregate_root import AbstractAggregateRoot

from spakky.data.persistency.aggregate_collector import AggregateCollector
from spakky.data.persistency.error import AggregateBufferNotOpenError


def test_collector_nested_buffer_expect_isolated_from_outer() -> None:
    """새 transaction buffer는 바깥 buffer와 섞이지 않고, 닫으면 바깥이 다시 보인다."""
    collector = AggregateCollector()
    outer = MagicMock(spec=AbstractAggregateRoot)
    inner = MagicMock(spec=AbstractAggregateRoot)

    collector.begin_transaction()
    collector.collect(outer)
    collector.begin_transaction()
    collector.collect(inner)
    assert collector.all() == [inner]

    collector.commit_transaction()

    assert collector.all() == [outer]
    assert collector.drain_committed() == [inner]


def test_collector_commit_expect_drain_once() -> None:
    """commit된 buffer는 drain_committed로 한 번만 꺼내진다."""
    collector = AggregateCollector()
    aggregate = MagicMock(spec=AbstractAggregateRoot)

    collector.begin_transaction()
    collector.collect(aggregate)
    collector.commit_transaction()

    assert collector.all() == []
    assert collector.drain_committed() == [aggregate]
    assert collector.drain_committed() == []


def test_collector_discard_expect_aggregates_dropped() -> None:
    """rollback된 buffer의 aggregate는 발행 대상으로 넘어가지 않는다."""
    collector = AggregateCollector()
    aggregate = MagicMock(spec=AbstractAggregateRoot)

    collector.begin_transaction()
    collector.collect(aggregate)
    collector.discard_transaction()

    assert collector.all() == []
    assert collector.drain_committed() == []


def test_collector_commit_without_begin_expect_buffer_not_open_error() -> None:
    """열지 않은 buffer를 commit하려 하면 AggregateBufferNotOpenError가 난다."""
    collector = AggregateCollector()

    with pytest.raises(AggregateBufferNotOpenError):
        collector.commit_transaction()


def test_collector_discard_without_begin_expect_buffer_not_open_error() -> None:
    """열지 않은 buffer를 버리려 하면 AggregateBufferNotOpenError가 난다."""
    collector = AggregateCollector()

    with pytest.raises(AggregateBufferNotOpenError):
        collector.discard_transaction()
