"""Tests for AbstractIntegrationEvent partition key exposure."""

from typing import override

from spakky.core.common.mutability import immutable

from spakky.domain.models.event import AbstractIntegrationEvent


def test_integration_event_partition_key_defaults_to_none() -> None:
    """partition_key를 재정의하지 않은 integration event가 None을 반환함을 검증한다."""

    @immutable
    class SampleIntegrationEvent(AbstractIntegrationEvent):
        order_id: str

    assert SampleIntegrationEvent(order_id="ORD-1").partition_key is None


def test_integration_event_partition_key_override_returns_declared_value() -> None:
    """partition_key를 재정의한 integration event가 그 값을 반환함을 검증한다."""

    @immutable
    class OrderScopedIntegrationEvent(AbstractIntegrationEvent):
        order_id: str

        @property
        @override
        def partition_key(self) -> str | None:
            return self.order_id

    assert OrderScopedIntegrationEvent(order_id="ORD-2").partition_key == "ORD-2"
