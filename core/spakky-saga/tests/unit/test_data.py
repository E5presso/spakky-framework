"""Unit tests for AbstractSagaData."""

from abc import ABC
from dataclasses import FrozenInstanceError
from uuid import UUID

import pytest
from spakky.core.common.mutability import immutable
from spakky.domain.models.base import AbstractDomainModel
from spakky.saga.data import AbstractSagaData


@immutable
class _ConcreteSagaData(AbstractSagaData):
    order_id: UUID


def test_abstract_saga_data_inheritance_expect_abstract_domain_model() -> None:
    """AbstractSagaData가 AbstractDomainModel을 상속하는지 검증한다."""
    assert issubclass(AbstractSagaData, AbstractDomainModel)


def test_abstract_saga_data_is_abc_expect_true() -> None:
    """AbstractSagaData가 ABC 서브클래스인지 검증한다."""
    assert issubclass(AbstractSagaData, ABC)


def test_concrete_saga_data_saga_id_default_expect_uuid() -> None:
    """saga_id가 기본값으로 UUID를 생성하는지 검증한다."""
    order_id = UUID("12345678-1234-5678-1234-567812345678")
    data = _ConcreteSagaData(order_id=order_id)
    assert isinstance(data.saga_id, UUID)


def test_concrete_saga_data_saga_id_explicit_expect_preserved() -> None:
    """명시적으로 지정한 saga_id가 유지되는지 검증한다."""
    saga_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    order_id = UUID("12345678-1234-5678-1234-567812345678")
    data = _ConcreteSagaData(saga_id=saga_id, order_id=order_id)
    assert data.saga_id == saga_id


def test_concrete_saga_data_frozen_expect_frozen_instance_error() -> None:
    """AbstractSagaData가 frozen dataclass인지 검증한다."""
    order_id = UUID("12345678-1234-5678-1234-567812345678")
    data = _ConcreteSagaData(order_id=order_id)
    with pytest.raises(FrozenInstanceError):
        data.saga_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")  # type: ignore[misc]


def test_concrete_saga_data_custom_fields_expect_accessible() -> None:
    """서브클래스의 커스텀 필드에 접근 가능한지 검증한다."""
    order_id = UUID("12345678-1234-5678-1234-567812345678")
    data = _ConcreteSagaData(order_id=order_id)
    assert data.order_id == order_id


def test_concrete_saga_data_unique_saga_ids_expect_different() -> None:
    """각 인스턴스가 고유한 saga_id를 가지는지 검증한다."""
    order_id = UUID("12345678-1234-5678-1234-567812345678")
    data1 = _ConcreteSagaData(order_id=order_id)
    data2 = _ConcreteSagaData(order_id=order_id)
    assert data1.saga_id != data2.saga_id
