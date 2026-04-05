"""Unit tests for AbstractSagaData model."""

from dataclasses import FrozenInstanceError
from uuid import UUID

from spakky.core.common.mutability import immutable
from spakky.domain.models.base import AbstractDomainModel
from spakky.saga.models.saga_data import AbstractSagaData


def test_abstract_saga_data_inherits_abstract_domain_model() -> None:
    """AbstractSagaData가 AbstractDomainModel을 상속하는지 검증한다."""
    assert issubclass(AbstractSagaData, AbstractDomainModel)


def test_abstract_saga_data_has_saga_id_field() -> None:
    """AbstractSagaData 서브클래스가 saga_id UUID 필드를 포함하는지 검증한다."""

    @immutable
    class MySagaData(AbstractSagaData):
        order_id: str

    data = MySagaData(order_id="ORD-001")
    assert isinstance(data.saga_id, UUID)


def test_abstract_saga_data_is_immutable() -> None:
    """AbstractSagaData 서브클래스가 불변(frozen)인지 검증한다."""

    @immutable
    class MySagaData(AbstractSagaData):
        order_id: str

    data = MySagaData(order_id="ORD-001")
    try:
        data.order_id = "ORD-002"  # type: ignore
        raise AssertionError("Expected FrozenInstanceError")
    except FrozenInstanceError:
        pass


def test_abstract_saga_data_custom_saga_id() -> None:
    """AbstractSagaData에 직접 saga_id를 지정할 수 있는지 검증한다."""

    @immutable
    class MySagaData(AbstractSagaData):
        value: int

    custom_id = UUID("12345678-1234-5678-1234-567812345678")
    data = MySagaData(saga_id=custom_id, value=42)
    assert data.saga_id == custom_id
    assert data.value == 42


def test_abstract_saga_data_auto_generates_unique_ids() -> None:
    """AbstractSagaData가 인스턴스마다 고유한 saga_id를 생성하는지 검증한다."""

    @immutable
    class MySagaData(AbstractSagaData):
        value: int

    data1 = MySagaData(value=1)
    data2 = MySagaData(value=2)
    assert data1.saga_id != data2.saga_id


def test_abstract_saga_data_keyword_only_init() -> None:
    """AbstractSagaData가 키워드 전용 초기화를 강제하는지 검증한다."""

    @immutable
    class MySagaData(AbstractSagaData):
        value: int

    try:
        MySagaData(42)  # type: ignore
        raise AssertionError("Expected TypeError")
    except TypeError:
        pass
