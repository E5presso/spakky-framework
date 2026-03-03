import pytest

from spakky.core.pod.annotations.order import Order


def test_order_cannot_be_negative() -> None:
    """Order 값이 음수일 때 ValueError가 발생함을 검증한다."""
    with pytest.raises(ValueError, match="Order cannot be negative"):
        Order(-1)
