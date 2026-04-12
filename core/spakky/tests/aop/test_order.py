import pytest

from spakky.core.pod.annotations.order import Order
from spakky.core.pod.error import NegativeOrderValueError


def test_order_cannot_be_negative() -> None:
    """Order 값이 음수일 때 NegativeOrderValueError가 발생함을 검증한다."""
    with pytest.raises(NegativeOrderValueError):
        Order(-1)
